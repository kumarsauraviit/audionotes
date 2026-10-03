import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

import app.gnani_client as gnani
from app.analysis import build_chapters, extract_structured
from app.audio_probe import AudioMetadata, AudioProbeError, probe_audio
from app.config import get_settings
from app.database import SessionLocal
from app.errors import ProcessingError
from app.gemini import GeminiNotConfigured, generate_text_with_model
from app.gnani_client import TranscriptionOptions
from app.models import AudioNote, ErrorCode, ProcessingStatus, SummaryStatus
from app.supabase_storage import download_audio_from_supabase, is_supabase_ref

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".amr"}

# Rough throughput assumption used only to estimate progress for long jobs.
PROCESSING_REALTIME_FACTOR = 0.6
MIN_ESTIMATE_SECONDS = 45


def _set_state(note_id: str, status: ProcessingStatus, **values) -> None:
    with SessionLocal() as db:
        note = db.get(AudioNote, note_id)
        if note:
            note.status = status
            for key, value in values.items():
                setattr(note, key, value)
            db.commit()


def _set_progress(
    note_id: str,
    stage: str,
    percent: int,
    message: str,
    *,
    eta_seconds: int | None = None,
    gnani_status: str | None = None,
) -> None:
    values: dict = {
        "stage": stage,
        "progress_percent": max(0, min(100, percent)),
        "progress_message": message,
        "eta_seconds": eta_seconds,
    }
    if gnani_status is not None:
        values["gnani_status"] = gnani_status
    with SessionLocal() as db:
        note = db.get(AudioNote, note_id)
        if note:
            for key, value in values.items():
                setattr(note, key, value)
            db.commit()


async def _load_audio_bytes(file_source: str) -> bytes:
    if file_source.startswith(("http://", "https://")) or is_supabase_ref(file_source):
        return await asyncio.to_thread(download_audio_from_supabase, file_source)
    path = Path(file_source)
    if not path.exists():
        raise ProcessingError(ErrorCode.storage_error, "The stored audio file could not be found.")
    return await asyncio.to_thread(path.read_bytes)


def _estimate_eta(duration_seconds: float | None, elapsed: float) -> int | None:
    """Very rough remaining-time estimate for user reassurance, never negative."""
    if not duration_seconds:
        return None
    total_estimate = max(MIN_ESTIMATE_SECONDS, duration_seconds * PROCESSING_REALTIME_FACTOR)
    remaining = total_estimate - elapsed
    if remaining <= 0:
        return 0
    return int(remaining)


def _transcribing_percent(duration_seconds: float | None, elapsed: float, gnani_status: str | None) -> int:
    if gnani_status in ("CREATED", "STARTING", "QUEUED"):
        return min(18, 12 + int(elapsed / 10))
    if not duration_seconds:
        # Fall back to a slow asymptotic crawl.
        return min(84, 20 + int(elapsed / 6))
    total_estimate = max(MIN_ESTIMATE_SECONDS, duration_seconds * PROCESSING_REALTIME_FACTOR)
    ratio = min(elapsed / total_estimate, 0.97)
    return 20 + int(64 * ratio)


async def _poll_until_terminal(note_id: str, job_id: str, duration_seconds: float | None) -> dict:
    settings = get_settings()
    interval = max(settings.gnani_poll_interval_seconds, 10)
    max_polls = max(1, settings.gnani_max_poll_seconds // interval)
    start = asyncio.get_event_loop().time()
    last_status: str | None = None

    terminal_ok = {"COMPLETED", "PARTIAL_FAILURE"}
    terminal_bad = {"FAILED", "START_FAILED", "CANCELLED"}

    for _ in range(max_polls):
        await asyncio.sleep(interval)
        elapsed = asyncio.get_event_loop().time() - start
        try:
            data = await gnani.get_batch_job(job_id)
        except ProcessingError:
            raise
        except Exception as exc:  # transient poll failure — keep trying
            logger.warning("Poll of Gnani job %s failed: %s", job_id, exc)
            continue

        last_status = data.get("status")
        job_progress = data.get("progress") or {}
        _set_progress(
            note_id,
            "transcribing",
            _transcribing_percent(duration_seconds, elapsed, last_status),
            _transcribing_message(last_status, job_progress),
            eta_seconds=_estimate_eta(duration_seconds, elapsed),
            gnani_status=last_status,
        )

        if last_status in terminal_ok:
            return data
        if last_status in terminal_bad:
            reason = data.get("cancel_reason") or data.get("message") or f"Job entered {last_status} state."
            code = ErrorCode.gnani_rejected
            if data.get("cancel_reason") and "path" in str(data.get("cancel_reason")).lower():
                code = ErrorCode.storage_error
            raise ProcessingError(code, f"Transcription failed: {reason}")

    raise ProcessingError(ErrorCode.gnani_timeout, retryable=True)


def _transcribing_message(gnani_status: str | None, job_progress: dict) -> str:
    if gnani_status in ("CREATED", "STARTING"):
        return "Sending your audio to Gnani"
    if gnani_status == "QUEUED":
        return "Queued at Gnani — waiting for a worker"
    if gnani_status == "IN_PROGRESS":
        total = job_progress.get("total_files")
        if total:
            return "Gnani is transcribing your audio"
        return "Listening to every word"
    return "Transcribing"


def _parse_transcript_payload(payload: dict, keep_speakers: bool = True) -> tuple[str, list[dict], str | None, float | None]:
    transcript = (payload.get("full_transcript") or "").strip()
    segments: list[dict] = []
    for segment in payload.get("segments") or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        try:
            start_time = float(segment.get("start_time") or 0.0)
            end_time = float(segment.get("end_time") or 0.0)
        except (TypeError, ValueError):
            continue
        # Gnani returns a speaker_id even when diarization was not requested, so
        # only keep it when the user actually asked for speaker separation.
        speaker = segment.get("speaker_id") if keep_speakers else None
        try:
            confidence = float(segment["confidence"]) if segment.get("confidence") is not None else None
        except (TypeError, ValueError):
            confidence = None
        segments.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "text": text,
                "speaker_id": speaker if isinstance(speaker, int) else None,
                "confidence": confidence,
            }
        )
    detected_language = payload.get("language_code")
    try:
        duration = float(payload["duration_seconds"]) if payload.get("duration_seconds") is not None else None
    except (TypeError, ValueError):
        duration = None
    return transcript, segments, detected_language, duration
    

async def _transcribe_with_rest(
    note_id: str,
    file_source: str,
    language_code: str,
    duration_seconds: float | None,
) -> dict:
    _set_progress(note_id, "transcribing", 30, "Transcribing with number & date formatting")
    audio_bytes = await _load_audio_bytes(file_source)
    file_name = Path(str(file_source).split("?")[0]).name or "audio.wav"
    transcript = await gnani.transcribe_rest(
        language_code=language_code,
        audio_bytes=audio_bytes,
        file_name=file_name,
        use_itn=True,
    )
    detected = language_code.split(",")[0].strip() or None
    return {
        "transcript": transcript,
        "engine": "Gnani REST STT (ITN)",
        "segments": [],
        "detected_language": detected,
        "duration_seconds": duration_seconds,
        "gnani_job_id": None,
        "gnani_request_id": None,
    }


async def _transcribe_with_batch(
    note_id: str,
    file_source: str,
    language_code: str,
    options: TranscriptionOptions,
    duration_seconds: float | None,
) -> dict:
    settings = get_settings()
    # Prefer ingesting by reference so we avoid re-uploading bytes and the 10 MB cap.
    source_url: str | None = None
    if settings.gnani_cloud_ingest:
        if is_supabase_ref(file_source) or file_source.startswith(("http://", "https://")):
            from app.supabase_storage import create_signed_url

            source_url = await asyncio.to_thread(create_signed_url, file_source)
            if not source_url and file_source.startswith(("http://", "https://")):
                source_url = file_source

    audio_bytes: bytes | None = None
    file_name = Path(str(file_source).split("?")[0]).name or "audio.wav"
    if source_url:
        _set_progress(note_id, "transcribing", 12, "Sending your audio to Gnani")
    else:
        _set_progress(note_id, "transcribing", 8, "Uploading audio to Gnani")
        audio_bytes = await _load_audio_bytes(file_source)

    job_id, request_id = await gnani.create_batch_job(
        language_code=language_code,
        options=options,
        source_url=source_url,
        audio_bytes=audio_bytes,
        file_name=file_name,
    )
    _set_state(note_id, ProcessingStatus.transcribing, gnani_job_id=job_id, gnani_request_id=request_id)
    _set_progress(note_id, "transcribing", 15, "Starting transcription", gnani_status="CREATED")

    await gnani.start_batch_job(job_id)
    data = await _poll_until_terminal(note_id, job_id, duration_seconds)
    status = data.get("status")

    if status == "PARTIAL_FAILURE":
        logger.warning("Gnani job %s completed with partial failure", job_id)

    _set_progress(note_id, "transcribing", 88, "Fetching your transcript", gnani_status=status)

    files = await gnani.get_batch_job_files(job_id, status="COMPLETED")
    if not files:
        # Surface the underlying file error where possible.
        failed = await gnani.get_batch_job_files(job_id, status="FAILED")
        detail = failed[0].get("error_message") if failed else ""
        if detail and "empty transcript" in detail.lower():
            raise ProcessingError(ErrorCode.no_speech)
        if detail:
            raise ProcessingError(ErrorCode.gnani_rejected, f"Gnani could not process this file: {detail}")
        raise ProcessingError(ErrorCode.no_speech)

    entry = files[0]
    transcript_url = entry.get("transcript_url")
    if not transcript_url:
        error_message = entry.get("error_message") or "No transcript URL was returned."
        if "empty transcript" in error_message.lower():
            raise ProcessingError(ErrorCode.no_speech)
        raise ProcessingError(ErrorCode.gnani_rejected, error_message)

    payload = await gnani.download_transcript(transcript_url)
    transcript, segments, detected_language, reported_duration = _parse_transcript_payload(
        payload, keep_speakers=options.with_diarization
    )
    if not transcript:
        raise ProcessingError(ErrorCode.no_speech)

    return {
        "transcript": transcript,
        "engine": "Gnani Batch STT (v3)",
        "segments": segments,
        "detected_language": detected_language,
        "duration_seconds": reported_duration or duration_seconds,
        "gnani_job_id": job_id,
        "gnani_request_id": request_id,
    }


async def _transcribe(note: AudioNote) -> dict:
    settings = get_settings()
    options = TranscriptionOptions(
        language_code=note.language_code,
        with_diarization=bool(note.with_diarization),
        num_speakers=settings.gnani_default_num_speakers,
        with_denoise=bool(note.with_denoise),
        bias_list=list(note.bias_list or []),
        bias_score=note.bias_score,
    )

    duration = note.duration_seconds
    use_rest = (
        duration is not None
        and duration <= settings.gnani_rest_itn_max_seconds
        and not options.with_diarization
        and not options.with_denoise
    )
    if use_rest:
        return await _transcribe_with_rest(note.id, note.file_path, note.language_code, duration)
    return await _transcribe_with_batch(note.id, note.file_path, note.language_code, options, duration)


async def _summarize(transcript: str) -> tuple[str, str]:
    prompt = (
        "Summarize this audio transcript in clear, concise language. Use a short overview and "
        "bullet points for key ideas or action items when relevant. Do not invent details.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )
    return await asyncio.to_thread(generate_text_with_model, prompt)


async def process_note(note_id: str) -> None:
    with SessionLocal() as db:
        note = db.get(AudioNote, note_id)
        if not note:
            return
        duration_seconds = note.duration_seconds

    try:
        _set_progress(note_id, "preparing", 3, "Getting your audio ready", gnani_status=None)

        result = await _transcribe(note)

        if not result["transcript"]:
            raise ProcessingError(ErrorCode.no_speech)

        _set_state(
            note_id,
            ProcessingStatus.summarizing,
            transcript=result["transcript"],
            transcription_engine=result["engine"],
            segments=result["segments"],
            detected_language=result["detected_language"],
            duration_seconds=result["duration_seconds"],
            gnani_job_id=result["gnani_job_id"],
            gnani_request_id=result["gnani_request_id"],
            error_code=None,
            error_message=None,
        )
        _set_progress(note_id, "summarizing", 92, "Finding the important bits")

        summary: str | None = None
        summary_model: str | None = None
        summary_status = SummaryStatus.pending
        try:
            summary, summary_model = await _summarize(result["transcript"])
            summary_status = SummaryStatus.ready
        except GeminiNotConfigured:
            summary_status = SummaryStatus.skipped
            logger.warning("Summary skipped: Gemini not configured")
        except Exception as exc:  # noqa: BLE001
            summary_status = SummaryStatus.failed
            logger.warning("Summary generation failed: %s", exc)

        # Structured extraction + chapters are best-effort derived data.
        extraction = await asyncio.to_thread(extract_structured, result["transcript"])
        chapters = await asyncio.to_thread(build_chapters, result["segments"], result["transcript"])

        with SessionLocal() as db:
            note = db.get(AudioNote, note_id)
            if note:
                note.summary = summary
                note.summary_model = summary_model
                note.summary_status = summary_status
                note.extraction = extraction
                note.chapters = chapters
                db.commit()

        _set_progress(note_id, "finalizing", 96, "Finishing up")

        final_status = (
            ProcessingStatus.complete if summary_status == SummaryStatus.ready else ProcessingStatus.complete_with_warnings
        )
        _set_state(
            note_id,
            final_status,
            stage="complete",
            progress_percent=100,
            progress_message="Ready",
            eta_seconds=0,
            error_code=None,
            error_message=None,
        )
        logger.info("Finished processing note %s (%s, summary=%s)", note_id, final_status.value, summary_status.value)
    except ProcessingError as exc:
        logger.warning("Processing failed for note %s (%s): %s", note_id, exc.code, exc.user_message)
        _set_state(
            note_id,
            ProcessingStatus.failed,
            error_code=exc.code,
            error_message=exc.user_message,
            stage="failed",
            progress_message=exc.user_message,
            eta_seconds=None,
        )
    except AudioProbeError as exc:
        _set_state(
            note_id,
            ProcessingStatus.failed,
            error_code=ErrorCode.corrupt_audio.value,
            error_message=str(exc),
            stage="failed",
        )
    except httpx.RequestError as exc:
        logger.exception("Network error while processing note %s", note_id)
        _set_state(
            note_id,
            ProcessingStatus.failed,
            error_code=ErrorCode.gnani_unavailable.value,
            error_message="We couldn’t reach the transcription service. Please retry.",
            stage="failed",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed for audio note %s", note_id)
        _set_state(
            note_id,
            ProcessingStatus.failed,
            error_code=ErrorCode.internal_error.value,
            error_message="Something went wrong while processing this recording.",
            stage="failed",
        )


def recover_stale_jobs() -> int:
    """Re-queue notes that were left mid-flight (e.g. a worker died)."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stale_job_minutes)
    in_flight = (
        ProcessingStatus.queued,
        ProcessingStatus.transcribing,
        ProcessingStatus.summarizing,
        ProcessingStatus.indexing,
    )
    requeued: list[str] = []
    with SessionLocal() as db:
        notes = db.scalars(
            select(AudioNote).where(AudioNote.status.in_(in_flight), AudioNote.updated_at < cutoff)
        ).all()
        for note in notes:
            note.status = ProcessingStatus.queued
            note.stage = "queued"
            note.progress_percent = 0
            note.progress_message = "Re-queued after an interruption"
            note.retry_count = (note.retry_count or 0) + 1
            requeued.append(note.id)
        if requeued:
            db.commit()

    for note_id in requeued:
        try:
            from app.tasks import process_note_task

            process_note_task.delay(note_id)
            logger.info("Re-queued stale note %s", note_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not re-queue stale note %s: %s", note_id, exc)
    return len(requeued)


def probe_upload(data: bytes, filename: str) -> AudioMetadata:
    """Validate an upload before it is accepted. Raises ProcessingError on failure."""
    try:
        return probe_audio(data, filename)
    except AudioProbeError as exc:
        raise ProcessingError(ErrorCode.corrupt_audio, str(exc)) from exc
