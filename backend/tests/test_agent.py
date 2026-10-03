"""Tests for the transcript agent tools and the endpoints that use them.

The LLM itself is not exercised here; we test the deterministic transcript tools
and mock the agent call for the HTTP endpoints.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.tools import (
    NoteContext,
    get_details,
    list_chapters,
    open_moment,
    read_transcript,
    search_library,
    search_transcript,
)
from app.database import Base, get_db
from app.main import app
from app.models import AudioNote, ProcessingStatus, User
from app.security import create_access_token, hash_password


SEGMENTS = [
    {"start_time": 0.0, "end_time": 4.0, "text": "Welcome to the quarterly roadmap meeting.", "speaker_id": 1},
    {"start_time": 4.0, "end_time": 9.0, "text": "We decided to ship version 2.0 by December.", "speaker_id": 2},
    {"start_time": 9.0, "end_time": 14.0, "text": "Priya will own the release and the beta invites.", "speaker_id": 1},
    {"start_time": 14.0, "end_time": 20.0, "text": "The marketing budget was not discussed today.", "speaker_id": 2},
]


def make_context(note_id: str = "ctx_1") -> NoteContext:
    return NoteContext(
        id=note_id,
        filename="roadmap.mp3",
        duration_seconds=20.0,
        transcript=" ".join(segment["text"] for segment in SEGMENTS),
        summary="Ship v2.0 by December; Priya owns the release.",
        segments=SEGMENTS,
        chapters=[{"title": "Roadmap", "start_time": 0.0, "end_time": 9.0, "summary": "Goals"}],
        speaker_labels={"1": "Host", "2": "Guest"},
        tags=["planning"],
    )


def test_search_transcript_returns_timestamped_moments():
    ctx = make_context()
    result = search_transcript(ctx, "release", max_results=5)
    assert result["count"] >= 1
    top = result["matches"][0]
    assert top["start_time"] == 9.0
    assert top["speaker"] == "Host"
    assert "release" in top["text"].lower()


def test_search_transcript_phrase_priority():
    ctx = make_context()
    result = search_transcript(ctx, "marketing budget", max_results=3)
    assert result["count"] == 1
    assert result["matches"][0]["start_time"] == 14.0


def test_open_moment_reads_a_window():
    ctx = make_context()
    result = open_moment(ctx, 4.0, 6.0)
    assert "[00:04]" in result["text"]
    assert "version 2.0" in result["text"]
    assert len(result["segments"]) >= 1


def test_list_chapters_and_details():
    ctx = make_context()
    assert list_chapters(ctx)["chapters"][0]["title"] == "Roadmap"
    details = get_details(ctx)
    assert details["speakers"]["Host"] == 9.0
    assert details["tags"] == ["planning"]
    assert details["transcript_chars"] > 0


def test_read_transcript_pages_in_chunks():
    long_text = " ".join(f"segment {index} about the release plan and the beta invites" for index in range(200))
    ctx = NoteContext(id="long", filename="long.mp3", transcript=long_text, duration_seconds=600)
    first = read_transcript(ctx, 0, 500)
    assert first["offset"] == 0
    assert first["next_offset"] == 500
    assert first["text"]
    second = read_transcript(ctx, first["next_offset"], 500)
    assert second["offset"] == 500
    past_end = read_transcript(ctx, 10_000_000)
    assert past_end["text"] == ""
    assert past_end["next_offset"] is None


def test_search_library_across_notes():
    contexts = [make_context("a"), make_context("b")]
    hits = search_library(contexts, "marketing", limit=5)
    assert len(hits) == 2
    assert hits[0]["start_time"] == 14.0
    assert {hit["note_id"] for hit in hits} == {"a", "b"}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

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
        email="agent@example.com",
        name="Agent Tester",
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


def _note(db_session, user, note_id="agent_note_1") -> AudioNote:
    note = AudioNote(
        id=note_id,
        user_id=user.id,
        filename="roadmap.mp3",
        file_path="supabase://audio-notes/roadmap.mp3",
        file_size=1024,
        language_code="en-IN",
        status=ProcessingStatus.complete,
        transcript=" ".join(segment["text"] for segment in SEGMENTS),
        summary="Ship v2.0 by December.",
        segments=SEGMENTS,
    )
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    return note


def test_library_search_endpoint(client, db_session, verified_user, auth_headers):
    _note(db_session, verified_user)
    response = client.get("/api/search?q=release", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["hits"]
    assert body["hits"][0]["filename"] == "roadmap.mp3"


def test_ask_endpoint_uses_agent(client, db_session, verified_user, auth_headers):
    note = _note(db_session, verified_user)
    fake = {
        "answer": "Version 2.0 ships by December (00:04).",
        "sources": [{"content": "We decided to ship version 2.0 by December.", "start_time": 4.0, "end_time": 9.0}],
    }
    with patch("app.main.answer_question", return_value=fake) as mocked:
        response = client.post(
            f"/api/notes/{note.id}/ask",
            json={"question": "When do we ship?", "history": [{"question": "hi", "answer": "hello"}]},
            headers=auth_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert "December" in body["answer"]
    assert body["sources"][0]["start_time"] == 4.0
    mocked.assert_called_once()
    # The agent receives the note context and prior conversation history.
    _ctx, question, history = mocked.call_args.args
    assert question == "When do we ship?"
    assert history[0]["question"] == "hi"
