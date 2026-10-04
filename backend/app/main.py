import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.audio_compression import (
    MAX_GNANI_AUDIO_BYTES,
    AudioCompressionError,
    compress_for_transcription,
)
from app.database import Base, engine, get_db
from app.errors import ProcessingError
from app.gnani_client import synthesize_speech
from app.logging_utils import configure_logging, new_request_id, request_id_var
from app.models import AudioNote, ProcessingStatus, SummaryStatus, User
from app.schemas import (
    BulkUploadResponse,
    BulkUploadResult,
    GlossaryOut,
    GlossaryUpdate,
    LibrarySearchHit,
    LibrarySearchResponse,
    NoteOptionsUpdate,
    NoteOut,
    NoteUpdate,
    QuestionRequest,
    QuestionResponse,
    TranscriptUpdate,
    TTSRequest,
    UsageOut,
)
from app.agent import NoteContext, answer_question, iter_agent, search_library as search_library_notes
from app.security import (
    bearer_scheme,
    get_current_verified_user,
    get_current_verified_user_from_token_or_header,
)
from app.services import SUPPORTED_EXTENSIONS, process_note, probe_upload, recover_stale_jobs
from app.supabase_storage import (
    create_signed_url,
    delete_audio_from_supabase,
    ensure_bucket_exists,
    is_supabase_enabled,
    is_supabase_ref,
    upload_audio_to_supabase,
)
from app.tasks import process_note_task
from app.auth_routes import router as auth_router

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
SUPPORTED_BATCH_LANGUAGES = {"bn-IN", "en-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "ta-IN", "te-IN"}
SUPPORTED_REST_LANGUAGES = SUPPORTED_BATCH_LANGUAGES | {"gu-IN", "pa-IN"}

app = FastAPI(title="Audio Notes API", version="0.2.0")


# Columns added since the initial schema, so a fresh local dev DB works without
# running Alembic. Kept idempotent and Postgres-specific.
_ADDED_COLUMNS: list[tuple[str, str, str | None]] = [
    ("transcription_engine", "VARCHAR(64)", None),
    ("summary_model", "VARCHAR(64)", None),
    ("segments", "JSON", None),
    ("user_id", "VARCHAR(36)", None),
    ("detected_language", "VARCHAR(16)", None),
    ("duration_seconds", "DOUBLE PRECISION", None),
    ("summary_status", "VARCHAR(16)", "'pending'"),
    ("extraction", "JSON", None),
    ("chapters", "JSON", None),
    ("speaker_labels", "JSON", None),
    ("tags", "JSON", None),
    ("stage", "VARCHAR(32)", None),
    ("progress_percent", "INTEGER", None),
    ("progress_message", "TEXT", None),
    ("eta_seconds", "INTEGER", None),
    ("gnani_status", "VARCHAR(32)", None),
    ("gnani_job_id", "VARCHAR(64)", None),
    ("gnani_request_id", "VARCHAR(128)", None),
    ("with_diarization", "BOOLEAN", "false"),
    ("with_denoise", "BOOLEAN", "false"),
    ("bias_list", "JSON", None),
    ("bias_score", "DOUBLE PRECISION", None),
    ("summary_audio_path", "VARCHAR(1024)", None),
    ("summary_audio_voice", "VARCHAR(64)", None),
    ("error_code", "VARCHAR(64)", None),
    ("retry_count", "INTEGER", "0"),
]


@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for name, sql_type, default in _ADDED_COLUMNS:
                default_clause = f" DEFAULT {default}" if default else ""
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE audio_notes ADD COLUMN IF NOT EXISTS {name} {sql_type}{default_clause}"
                    )
                except Exception:
                    pass
            for name, sql_type, default in (("glossary", "JSON", None), ("default_language", "VARCHAR(16)", None)):
                try:
                    default_clause = f" DEFAULT {default}" if default else ""
                    conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {sql_type}{default_clause}")
                except Exception:
                    pass
            for statement in (
                "ALTER TABLE audio_notes ALTER COLUMN language_code TYPE VARCHAR(32)",
                # status was VARCHAR(11) before "transcribing"/"complete_with_warnings";
                # widen it so existing Postgres databases accept the enum values.
                "ALTER TABLE audio_notes ALTER COLUMN status TYPE VARCHAR(32)",
                "CREATE INDEX IF NOT EXISTS ix_audio_notes_user_id ON audio_notes (user_id)",
                "CREATE INDEX IF NOT EXISTS ix_audio_notes_gnani_job_id ON audio_notes (gnani_job_id)",
            ):
                try:
                    conn.exec_driver_sql(statement)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("Could not auto-create database tables on startup: %s", exc)

    if is_supabase_enabled():
        try:
            ensure_bucket_exists()
        except Exception as exc:
            logger.warning("Could not auto-initialize Supabase bucket: %s", exc)

    if settings.gnani_use_webhook and not settings.gnani_webhook_base_url:
        logger.warning("GNANI_USE_WEBHOOK is on but GNANI_WEBHOOK_BASE_URL is not set; falling back to polling.")

    try:
        recovered = recover_stale_jobs()
        if recovered:
            logger.info("Recovered %d stale note(s) on startup", recovered)
    except Exception as exc:
        logger.warning("Stale job recovery failed: %s", exc)


app.include_router(auth_router)
frontend_origin = settings.frontend_origin.rstrip("/")
frontend_origins = {frontend_origin}
parsed_frontend_origin = urlsplit(frontend_origin)
if parsed_frontend_origin.hostname in {"localhost", "127.0.0.1", "::1"}:
    port = f":{parsed_frontend_origin.port}" if parsed_frontend_origin.port else ""
    local_hosts = {"localhost", "127.0.0.1", "[::1]"}
    local_hosts.discard(parsed_frontend_origin.hostname)
    for host in local_hosts:
        frontend_origins.add(
            urlunsplit((parsed_frontend_origin.scheme, f"{host}{port}", "", "", ""))
        )
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request, call_next):
    """Attach a correlation id to every request and log its outcome."""
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info("%s %s -> %s in %sms", request.method, request.url.path, response.status_code, duration_ms)
        return response
    finally:
        request_id_var.reset(token)


@app.get("/health")
def health():
    checks = {
        "supabase_storage": is_supabase_enabled(),
        "gnani_configured": bool(settings.gnani_api_key),
        "gemini_configured": bool(settings.gemini_api_key),
        "webhooks": settings.gnani_use_webhook,
        "cloud_ingest": settings.gnani_cloud_ingest,
    }
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False
    healthy = checks["database"]
    return {"status": "ok" if healthy else "degraded", **checks}


# --------------------------------------------------------------------------- #
# Upload helpers
# --------------------------------------------------------------------------- #

def _parse_language(value: str) -> str:
    codes = [code.strip() for code in (value or "").split(",") if code.strip()]
    if not codes:
        raise HTTPException(422, "Choose a language for this recording.")
    if len(codes) > 3:
        raise HTTPException(422, "You can identify at most three languages per recording.")
    for code in codes:
        if code not in SUPPORTED_REST_LANGUAGES:
            raise HTTPException(422, f"'{code}' is not a supported language for transcription.")
    return ",".join(codes)


def _parse_tags(value: str | None) -> list[str] | None:
    if not value:
        return None
    tags = [tag.strip() for tag in value.split(",") if tag.strip()]
    return tags[:20] or None


async def _ingest_upload(
    *,
    upload: UploadFile,
    language_code: str,
    allow_lossy_compression: bool,
    with_diarization: bool | None,
    with_denoise: bool | None,
    tags: str | None,
    current_user: User,
    db: Session,
) -> AudioNote:
    original_name = Path(upload.filename or "audio").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "Unsupported audio format. Use WAV, MP3, M4A, MP4, FLAC, OGG, OPUS, AAC, WEBM, or AMR.")
    language_code = _parse_language(language_code)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    payload = await upload.read(max_bytes + 1)
    if not payload:
        raise HTTPException(400, "The uploaded audio file is empty.")
    if len(payload) > max_bytes:
        raise HTTPException(413, f"Audio uploads must be {settings.max_upload_mb} MB or smaller.")

    if not is_supabase_enabled():
        raise HTTPException(500, "Supabase Storage is not configured. Please set SUPABASE_URL and keys in backend/.env.")

    # Preflight: reject corrupt files immediately and learn the duration.
    try:
        metadata = await asyncio.to_thread(probe_upload, payload, original_name)
    except ProcessingError as exc:
        raise HTTPException(422, exc.user_message) from exc

    stored_name = original_name
    content_type = upload.content_type
    # With cloud ingestion Gnani has no byte ceiling, so compression is only a
    # fallback for the multipart path.
    if not settings.gnani_cloud_ingest and len(payload) > MAX_GNANI_AUDIO_BYTES:
        if not allow_lossy_compression:
            raise HTTPException(
                409,
                "This audio is near Gnani’s 10 MB request limit. Lossy compression is required; confirm the quality warning before retrying.",
            )
        try:
            payload, stored_name, content_type = await asyncio.to_thread(
                compress_for_transcription, payload, original_name
            )
        except AudioCompressionError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.exception("Could not compress audio upload %s", original_name)
            raise HTTPException(503, "Audio compression failed. Please retry or choose another audio file.") from exc

    note_id = __import__("uuid").uuid4().hex
    try:
        file_name = f"{note_id}{Path(stored_name).suffix.lower()}"
        file_ref = await asyncio.to_thread(
            upload_audio_to_supabase, file_name=file_name, data=payload, content_type=content_type
        )
    except Exception as exc:
        logger.exception("Failed to upload audio to Supabase Storage")
        raise HTTPException(502, f"Failed to upload audio to Supabase Storage: {exc}")

    glossary = list(current_user.glossary or [])
    note = AudioNote(
        id=note_id,
        user_id=current_user.id,
        filename=original_name,
        file_path=file_ref,
        file_size=len(payload),
        language_code=language_code,
        duration_seconds=metadata.duration_seconds,
        status=ProcessingStatus.queued,
        stage="queued",
        progress_percent=0,
        progress_message="Waiting in queue",
        with_diarization=(
            with_diarization if with_diarization is not None else settings.gnani_default_diarization
        ),
        with_denoise=(with_denoise if with_denoise is not None else settings.gnani_default_denoise),
        bias_list=glossary or None,
        bias_score=settings.gnani_default_bias_score if glossary else None,
        tags=_parse_tags(tags),
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    process_note_task.delay(note_id)
    return note


# --------------------------------------------------------------------------- #
# Notes CRUD
# --------------------------------------------------------------------------- #

@app.post("/api/notes", response_model=NoteOut, status_code=202)
async def create_note(
    audio: UploadFile = File(...),
    language_code: str = Form("en-IN"),
    allow_lossy_compression: bool = Form(False),
    with_diarization: bool | None = Form(None),
    with_denoise: bool | None = Form(None),
    tags: str | None = Form(None),
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    return await _ingest_upload(
        upload=audio,
        language_code=language_code,
        allow_lossy_compression=allow_lossy_compression,
        with_diarization=with_diarization,
        with_denoise=with_denoise,
        tags=tags,
        current_user=current_user,
        db=db,
    )


@app.post("/api/notes/bulk", response_model=BulkUploadResponse, status_code=202)
async def create_notes_bulk(
    audio: list[UploadFile] = File(...),
    language_code: str = Form("en-IN"),
    with_diarization: bool | None = Form(None),
    with_denoise: bool | None = Form(None),
    tags: str | None = Form(None),
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    if len(audio) > 100:
        raise HTTPException(422, "You can upload up to 100 files at a time.")
    accepted: list[BulkUploadResult] = []
    rejected: list[BulkUploadResult] = []
    for upload in audio:
        filename = Path(upload.filename or "audio").name
        try:
            note = await _ingest_upload(
                upload=upload,
                language_code=language_code,
                allow_lossy_compression=True,
                with_diarization=with_diarization,
                with_denoise=with_denoise,
                tags=tags,
                current_user=current_user,
                db=db,
            )
            accepted.append(BulkUploadResult(filename=filename, note_id=note.id))
        except HTTPException as exc:
            rejected.append(BulkUploadResult(filename=filename, error=str(exc.detail)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Bulk upload failed for %s", filename)
            rejected.append(BulkUploadResult(filename=filename, error=str(exc)))
    return BulkUploadResponse(accepted=accepted, rejected=rejected)


@app.get("/api/notes", response_model=list[NoteOut])
def list_notes(
    q: str | None = None,
    search: str | None = None,
    status: str | None = None,
    language: str | None = None,
    tag: str | None = None,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    query_term = (q or search or "").strip()
    stmt = select(AudioNote).where(AudioNote.user_id == current_user.id).order_by(AudioNote.created_at.desc())
    if query_term:
        pattern = f"%{query_term}%"
        stmt = stmt.where(or_(AudioNote.filename.ilike(pattern), AudioNote.transcript.ilike(pattern), AudioNote.summary.ilike(pattern)))
    if status:
        stmt = stmt.where(AudioNote.status == status)
    if language:
        stmt = stmt.where(AudioNote.language_code.ilike(f"%{language}%"))
    notes = db.scalars(stmt).all()
    if tag:
        notes = [note for note in notes if tag in (note.tags or [])]
    return notes


@app.get("/api/notes/{note_id}", response_model=NoteOut)
def get_note(
    note_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    return note


@app.patch("/api/notes/{note_id}", response_model=NoteOut)
@app.put("/api/notes/{note_id}/rename", response_model=NoteOut)
def rename_note(
    note_id: str,
    payload: NoteUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    new_name = payload.filename.strip()
    if not new_name:
        raise HTTPException(422, "Filename cannot be empty.")
    note.filename = new_name
    db.commit()
    db.refresh(note)
    return note


@app.patch("/api/notes/{note_id}/options", response_model=NoteOut)
def update_note_options(
    note_id: str,
    payload: NoteOptionsUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    if payload.tags is not None:
        note.tags = [tag.strip() for tag in payload.tags if tag.strip()][:20] or None
    if payload.speaker_labels is not None:
        note.speaker_labels = payload.speaker_labels or None
    db.commit()
    db.refresh(note)
    return note


@app.patch("/api/notes/{note_id}/transcript", response_model=NoteOut)
def update_transcript(
    note_id: str,
    payload: TranscriptUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    if note.status not in (ProcessingStatus.complete, ProcessingStatus.complete_with_warnings):
        raise HTTPException(409, "Only finished recordings can be edited.")
    note.transcript = payload.transcript
    if payload.segments is not None:
        note.segments = [segment.model_dump() for segment in payload.segments]
    db.commit()
    db.refresh(note)
    return note


@app.get("/api/notes/{note_id}/audio")
def get_note_audio(
    note_id: str,
    token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    current_user = get_current_verified_user_from_token_or_header(token, credentials, db)
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id or not note.file_path:
        raise HTTPException(404, "Audio note not found.")

    # Hand out a short-lived signed URL and keep the bucket private.
    if is_supabase_ref(note.file_path) or note.file_path.startswith(("http://", "https://")):
        signed = create_signed_url(note.file_path)
        if signed:
            return RedirectResponse(url=signed, status_code=307)
        raise HTTPException(502, "Could not create a secure link for this audio. Please retry.")

    if not Path(note.file_path).exists():
        raise HTTPException(404, "Audio file not found on disk.")
    suffix = Path(note.file_path).suffix.lower()
    media_type = {
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
        ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".aac": "audio/aac",
        ".webm": "audio/webm", ".amr": "audio/amr",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path=note.file_path, media_type=media_type, filename=note.filename)


@app.get("/api/notes/{note_id}/summary-audio")
def get_summary_audio(
    note_id: str,
    token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    current_user = get_current_verified_user_from_token_or_header(token, credentials, db)
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id or not note.summary_audio_path:
        raise HTTPException(404, "No summary audio is available for this recording.")
    signed = create_signed_url(note.summary_audio_path)
    if not signed:
        raise HTTPException(502, "Could not create a secure link for this audio.")
    return RedirectResponse(url=signed, status_code=307)


@app.post("/api/notes/{note_id}/summary-audio", response_model=NoteOut, status_code=201)
async def create_summary_audio(
    note_id: str,
    payload: TTSRequest,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    if not note.summary or not note.summary.strip():
        raise HTTPException(409, "This recording does not have a summary to read aloud.")
    voice = (payload.voice or settings.gnani_tts_voice).strip() or settings.gnani_tts_voice
    language = (note.detected_language or note.language_code.split(",")[0] or "auto")
    try:
        audio_bytes = await synthesize_speech(note.summary, voice=voice, language=language)
    except ProcessingError as exc:
        raise HTTPException(502, exc.user_message) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("TTS failed for note %s", note_id)
        raise HTTPException(502, "Could not generate audio for the summary.") from exc

    try:
        file_name = f"{note.id}-summary.wav"
        note.summary_audio_path = await asyncio.to_thread(
            upload_audio_to_supabase,
            file_name=file_name,
            data=audio_bytes,
            content_type="audio/wav",
        )
        note.summary_audio_voice = voice
        db.commit()
        db.refresh(note)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Storing summary audio failed for note %s", note_id)
        raise HTTPException(502, "Generated the audio but could not store it. Please retry.") from exc
    return note


# --------------------------------------------------------------------------- #
# Processing lifecycle
# --------------------------------------------------------------------------- #

@app.post("/api/notes/{note_id}/retry", response_model=NoteOut, status_code=202)
def retry_note(
    note_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    if note.status != ProcessingStatus.failed:
        raise HTTPException(409, "Only failed recordings can be retried.")
    note.status = ProcessingStatus.queued
    note.stage = "queued"
    note.progress_percent = 0
    note.progress_message = "Waiting in queue"
    note.error_code = None
    note.error_message = None
    note.retry_count = (note.retry_count or 0) + 1
    db.commit()
    db.refresh(note)
    process_note_task.delay(note_id)
    return note


@app.post("/api/notes/{note_id}/ask", response_model=QuestionResponse)
def ask_question(
    note_id: str,
    payload: QuestionRequest,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    question_text = (payload.question or "").strip()
    if not question_text:
        raise HTTPException(422, "Question cannot be empty.")
    if not note.transcript or not note.transcript.strip():
        raise HTTPException(400, "This audio note does not have a transcript yet.")
    context = NoteContext.from_note(note)
    history = [turn.model_dump() for turn in payload.history]
    try:
        result = answer_question(context, question_text, history)
    except ValueError as val_err:
        raise HTTPException(422, str(val_err))
    except Exception:  # noqa: BLE001
        logger.exception("Agent question answering failed for note %s", note_id)
        raise HTTPException(503, "Question answering is temporarily unavailable. Please try again shortly.")
    return {
        "note_id": note_id,
        "question": question_text,
        "answer": result["answer"] or "I couldn't find an answer in this recording.",
        "sources": result["sources"],
    }


@app.post("/api/notes/{note_id}/ask/stream")
def ask_question_stream(
    note_id: str,
    payload: QuestionRequest,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    question_text = (payload.question or "").strip()
    if not question_text:
        raise HTTPException(422, "Question cannot be empty.")
    if not note.transcript or not note.transcript.strip():
        raise HTTPException(400, "This audio note does not have a transcript yet.")

    context = NoteContext.from_note(note)
    history = [turn.model_dump() for turn in payload.history]

    def event_stream():
        try:
            for event in iter_agent(context, question_text, history):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:  # noqa: BLE001
            logger.exception("Agent streaming failed for note %s", note_id)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Question answering failed. Please try again.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/search", response_model=LibrarySearchResponse)
def search_library(
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(8, ge=1, le=25),
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    try:
        notes = db.scalars(select(AudioNote).where(AudioNote.user_id == current_user.id)).all()
        contexts = [NoteContext.from_note(item) for item in notes]
        hits = search_library_notes(contexts, q, limit=limit) if contexts else []
    except Exception as exc:  # noqa: BLE001
        logger.exception("Library search failed")
        raise HTTPException(503, "Search is temporarily unavailable.") from exc
    return LibrarySearchResponse(query=q, hits=[LibrarySearchHit(**hit) for hit in hits])


@app.get("/api/usage", response_model=UsageOut)
def usage(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    notes = db.scalars(select(AudioNote).where(AudioNote.user_id == current_user.id)).all()
    total_seconds = sum(float(note.duration_seconds or 0.0) for note in notes)
    total_chars = sum(len(note.transcript or "") for note in notes)
    # Gnani pricing: STT ₹27/hour; TTS ₹27/10,000 characters.
    # TTS is estimated from the summary text for notes with saved summary audio,
    # applying the same character cap as the request sent to Gnani.
    tts_chars = sum(
        min(len(note.summary or ""), settings.gnani_tts_max_chars)
        for note in notes
        if note.summary_audio_path
    )
    stt_estimate = (total_seconds / 3600.0) * 27.0
    tts_estimate = (tts_chars / 10_000.0) * 27.0
    estimated = round(stt_estimate + tts_estimate, 2)
    return UsageOut(
        total_notes=len(notes),
        total_audio_seconds=round(total_seconds, 1),
        total_audio_minutes=round(total_seconds / 60.0, 1),
        total_transcript_chars=total_chars,
        total_tts_chars=tts_chars,
        stt_estimate_inr=round(stt_estimate, 2),
        tts_estimate_inr=round(tts_estimate, 2),
        credits_estimate_inr=estimated,
    )


# --------------------------------------------------------------------------- #
# Glossary (custom vocabulary)
# --------------------------------------------------------------------------- #

@app.get("/api/settings/glossary", response_model=GlossaryOut)
def get_glossary(current_user: User = Depends(get_current_verified_user)):
    return GlossaryOut(glossary=list(current_user.glossary or []), default_language=current_user.default_language)


@app.put("/api/settings/glossary", response_model=GlossaryOut)
def update_glossary(
    payload: GlossaryUpdate,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(404, "User not found.")
    user.glossary = payload.glossary or None
    if payload.default_language:
        user.default_language = payload.default_language
    db.commit()
    return GlossaryOut(glossary=payload.glossary, default_language=user.default_language)


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

def _format_timestamp(seconds: float, *, vtt: bool = False) -> str:
    if seconds < 0:
        seconds = 0.0
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{milliseconds:03d}"


def _build_subtitles(segments: Iterable[dict], *, vtt: bool, speaker_labels: dict | None = None) -> str:
    labels = speaker_labels or {}
    lines: list[str] = []
    if vtt:
        lines.append("WEBVTT")
        lines.append("")
    for index, segment in enumerate(segments, start=1):
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start_time") or 0.0)
        end = float(segment.get("end_time") or start)
        speaker = segment.get("speaker_id")
        label = ""
        if speaker is not None:
            name = labels.get(str(speaker)) or f"Speaker {speaker}"
            label = f"{name}: "
        lines.append(str(index))
        lines.append(f"{_format_timestamp(start, vtt=vtt)} --> {_format_timestamp(end, vtt=vtt)}")
        lines.append(f"{label}{text}")
        lines.append("")
    return "\n".join(lines)


def _build_markdown(note: AudioNote) -> str:
    labels = note.speaker_labels or {}
    parts: list[str] = [f"# {note.filename}", ""]
    if note.summary:
        parts += ["## Summary", "", note.summary, ""]
    extraction = note.extraction or {}
    if extraction.get("action_items"):
        parts += ["## Action items", ""]
        parts += [f"- {item}" for item in extraction["action_items"]]
        parts.append("")
    if extraction.get("decisions"):
        parts += ["## Decisions", ""]
        parts += [f"- {item}" for item in extraction["decisions"]]
        parts.append("")
    parts += ["## Transcript", ""]
    if note.segments:
        for segment in note.segments:
            start = float(segment.get("start_time") or 0.0)
            stamp = f"{int(start // 60):02d}:{int(start % 60):02d}"
            speaker = segment.get("speaker_id")
            label = ""
            if speaker is not None:
                name = labels.get(str(speaker)) or f"Speaker {speaker}"
                label = f"{name}: "
            parts.append(f"**[{stamp}]** {label}{segment.get('text', '').strip()}")
            parts.append("")
    else:
        parts += [note.transcript or "", ""]
    return "\n".join(parts)


@app.get("/api/notes/{note_id}/export")
def export_note(
    note_id: str,
    format: str = Query("txt", pattern="^(txt|md|srt|vtt)$"),
    token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    current_user = get_current_verified_user_from_token_or_header(token, credentials, db)
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    stem = Path(note.filename).stem or "transcript"

    if format in ("srt", "vtt"):
        if not note.segments:
            raise HTTPException(409, "Subtitles need timestamped segments, which this recording does not have.")
        content = _build_subtitles(note.segments, vtt=(format == "vtt"), speaker_labels=note.speaker_labels)
        media = "text/vtt" if format == "vtt" else "application/x-subrip"
        return PlainTextResponse(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'})

    if format == "md":
        return PlainTextResponse(
            _build_markdown(note),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{stem}.md"'},
        )

    return PlainTextResponse(
        note.transcript or "",
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{stem}.txt"'},
    )


# --------------------------------------------------------------------------- #
# Gnani webhook (best-effort; polling remains the source of truth)
# --------------------------------------------------------------------------- #

@app.post("/api/webhooks/gnani")
async def gnani_webhook(
    payload: dict,
    secret: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if settings.gnani_webhook_secret and secret != settings.gnani_webhook_secret:
        raise HTTPException(401, "Invalid webhook secret.")
    job_id = payload.get("job_id")
    status = payload.get("status")
    event = payload.get("event")
    logger.info("Gnani webhook: event=%s job=%s status=%s", event, job_id, status)
    if job_id:
        note = db.scalar(select(AudioNote).where(AudioNote.gnani_job_id == job_id))
        if note:
            note.gnani_status = status
            db.commit()
    return {"status": "received"}


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #

def _delete_note_assets(note: AudioNote) -> None:
    for path in (note.file_path, note.summary_audio_path):
        if not path:
            continue
        if is_supabase_ref(path) or path.startswith(("http://", "https://")):
            delete_audio_from_supabase(path)
        else:
            Path(path).unlink(missing_ok=True)


@app.delete("/api/notes/{note_id}", status_code=200)
def delete_note(
    note_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    note = db.get(AudioNote, note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(404, "Audio note not found.")
    _delete_note_assets(note)
    db.delete(note)
    db.commit()
    return {"status": "deleted", "id": note_id}


@app.delete("/api/notes", status_code=200)
def delete_all_notes(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    notes = db.scalars(select(AudioNote).where(AudioNote.user_id == current_user.id)).all()
    for note in notes:
        _delete_note_assets(note)
        db.delete(note)
    db.commit()
    return {"status": "cleared", "count": len(notes)}
