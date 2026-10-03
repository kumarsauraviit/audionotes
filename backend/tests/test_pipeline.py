"""Tests for the transcription pipeline's failure taxonomy, progress, exports,
glossary, usage, and the Gnani webhook."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.errors import ProcessingError, classify_gnani_http
from app.main import app
from app.models import AudioNote, ErrorCode, ProcessingStatus, User
from app.security import create_access_token, hash_password
from app.services import _estimate_eta, _transcribing_percent


@pytest.fixture(name="db_session")
def db_session_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(name="client")
def client_fixture(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(name="verified_user")
def verified_user_fixture(db_session):
    user = User(
        email="pipeline@example.com",
        name="Pipeline Tester",
        password_hash=hash_password("StrongPassword123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(verified_user):
    token, _ = create_access_token(verified_user)
    return {"Authorization": f"Bearer {token}"}


def test_gnani_error_classification():
    assert classify_gnani_http(401) == ErrorCode.gnani_auth
    assert classify_gnani_http(403) == ErrorCode.gnani_auth
    assert classify_gnani_http(429) == ErrorCode.gnani_rate_limit
    assert classify_gnani_http(503) == ErrorCode.gnani_unavailable
    assert classify_gnani_http(500) == ErrorCode.gnani_unavailable
    assert classify_gnani_http(400, "Audio duration exceeds maximum limit") == ErrorCode.file_too_large
    assert classify_gnani_http(400, "unsupported language") == ErrorCode.gnani_rejected


def test_processing_error_carries_safe_message():
    error = ProcessingError(ErrorCode.no_speech)
    assert error.code == "no_speech"
    assert "speech" in error.user_message.lower()
    assert error.retryable is False
    assert ProcessingError(ErrorCode.gnani_rate_limit, retryable=True).retryable is True


def test_progress_helpers_are_monotonic_and_bounded():
    for elapsed in range(0, 600, 30):
        percent = _transcribing_percent(120.0, float(elapsed), "IN_PROGRESS")
        assert 0 <= percent <= 100
    early = _transcribing_percent(600.0, 5.0, "IN_PROGRESS")
    late = _transcribing_percent(600.0, 300.0, "IN_PROGRESS")
    assert late > early
    assert _transcribing_percent(600.0, 1.0, "QUEUED") <= 18
    assert _estimate_eta(600.0, 20.0) is not None
    assert _estimate_eta(None, 20.0) is None


def test_glossary_validation_and_roundtrip(client, verified_user, auth_headers):
    # Invalid entries (spaces, digits) are rejected by the schema.
    bad = client.put("/api/settings/glossary", json={"glossary": ["has space"]}, headers=auth_headers)
    assert bad.status_code == 422
    bad_digit = client.put("/api/settings/glossary", json={"glossary": ["HDFC2"]}, headers=auth_headers)
    assert bad_digit.status_code == 422

    ok = client.put(
        "/api/settings/glossary",
        json={"glossary": ["Gnani", "Karnataka", "EMI"], "default_language": "kn-IN"},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    assert ok.json()["glossary"] == ["Gnani", "Karnataka", "EMI"]

    fetched = client.get("/api/settings/glossary", headers=auth_headers)
    assert fetched.status_code == 200
    assert "Gnani" in fetched.json()["glossary"]
    assert fetched.json()["default_language"] == "kn-IN"


def _complete_note(db_session, user) -> AudioNote:
    note = AudioNote(
        id="pipeline_note_1",
        user_id=user.id,
        filename="standup.mp3",
        file_path="supabase://audio-notes/pipeline_note_1.mp3",
        file_size=2048,
        language_code="en-IN",
        detected_language="en-IN",
        duration_seconds=132.0,
        status=ProcessingStatus.complete,
        transcript="We decided to ship on Friday. Priya owns the release.",
        summary="Ship on Friday; Priya owns the release.",
        segments=[
            {"start_time": 0.0, "end_time": 4.5, "text": "We decided to ship on Friday.", "speaker_id": 1},
            {"start_time": 4.5, "end_time": 9.0, "text": "Priya owns the release.", "speaker_id": 2},
        ],
    )
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    return note


def test_note_options_and_exports(client, db_session, verified_user, auth_headers):
    note = _complete_note(db_session, verified_user)

    options = client.patch(
        f"/api/notes/{note.id}/options",
        json={"tags": ["standup", "team"], "speaker_labels": {"1": "Host", "2": "Guest"}},
        headers=auth_headers,
    )
    assert options.status_code == 200
    assert options.json()["tags"] == ["standup", "team"]
    assert options.json()["speaker_labels"]["1"] == "Host"

    token = auth_headers["Authorization"].split(" ")[1]
    srt = client.get(f"/api/notes/{note.id}/export?format=srt&token={token}")
    assert srt.status_code == 200
    assert "00:00:00,000 --> 00:00:04,500" in srt.text
    assert "Host" in srt.text

    vtt = client.get(f"/api/notes/{note.id}/export?format=vtt&token={token}")
    assert vtt.status_code == 200
    assert vtt.text.startswith("WEBVTT")

    md = client.get(f"/api/notes/{note.id}/export?format=md&token={token}")
    assert md.status_code == 200
    assert "## Summary" in md.text and "## Transcript" in md.text

    # A recording without segments cannot be exported as subtitles.
    plain = AudioNote(
        id="pipeline_note_2",
        user_id=verified_user.id,
        filename="plain.mp3",
        file_path="supabase://audio-notes/plain.mp3",
        file_size=100,
        language_code="en-IN",
        status=ProcessingStatus.complete,
        transcript="hello",
        segments=None,
    )
    db_session.add(plain)
    db_session.commit()
    no_subs = client.get(f"/api/notes/{plain.id}/export?format=srt&token={token}")
    assert no_subs.status_code == 409


def test_usage_aggregation(client, db_session, verified_user, auth_headers):
    _complete_note(db_session, verified_user)
    response = client.get("/api/usage", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_notes"] >= 1
    assert body["total_audio_seconds"] >= 132.0
    assert body["total_transcript_chars"] > 0


def test_webhook_updates_gnani_status(client, db_session, verified_user):
    note = _complete_note(db_session, verified_user)
    note.status = ProcessingStatus.transcribing
    note.gnani_job_id = "job-123"
    db_session.commit()

    response = client.post(
        "/api/webhooks/gnani",
        json={"event": "job.completed", "job_id": "job-123", "status": "COMPLETED"},
    )
    assert response.status_code == 200
    db_session.refresh(note)
    assert note.gnani_status == "COMPLETED"
