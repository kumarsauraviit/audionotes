"""Thin, well-documented wrapper around the Gnani speech APIs.

Keeps every Gnani-specific detail (headers, retries, endpoints, request shapes)
in one place so the processing pipeline stays readable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.config import get_settings
from app.errors import ProcessingError, classify_gnani_http
from app.models import ErrorCode

logger = logging.getLogger(__name__)

BATCH_JOBS = "/stt/v3/batch/jobs"
REST_TRANSCRIBE = "/stt/v3"
TTS_INFERENCE = "/api/v1/tts/inference"

MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
    ".amr": "audio/amr",
}


@dataclass
class TranscriptionOptions:
    language_code: str
    with_diarization: bool = False
    num_speakers: int = 2
    with_denoise: bool = False
    bias_list: list[str] = field(default_factory=list)
    bias_score: float | None = None

    def to_config(self) -> dict:
        config: dict = {
            "model": "gnani-prisma-v2.5",
            "language_code": self.language_code,
            "mode": "transcribe",
            "with_diarization": self.with_diarization,
            "is_multi_channel": False,
            "with_denoise": self.with_denoise,
        }
        if self.with_diarization:
            config["num_speakers"] = min(max(self.num_speakers, 1), 2)
        if self.bias_list and self.bias_score:
            config["bias_list"] = self.bias_list[:100]
            config["bias_score"] = self.bias_score
        return config


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.gnani_api_key:
        raise ProcessingError(
            ErrorCode.gnani_auth,
            "The transcription service is not configured. Add GNANI_API_KEY to backend/.env.",
        )
    return {"X-API-Key-ID": settings.gnani_api_key}


def _new_request_id() -> str:
    return f"audionotes-{uuid.uuid4().hex[:16]}"


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 5,
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
    **kwargs,
) -> httpx.Response:
    """Retry transient Gnani failures with linear backoff."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in retry_statuses:
                delay = min(2.0 * (attempt + 1), 20.0)
                logger.warning(
                    "Gnani %s %s returned %s. Retrying in %.1fs (attempt %d/%d).",
                    method, url, response.status_code, delay, attempt + 1, max_attempts,
                )
                await asyncio.sleep(delay)
                continue
            return response
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            delay = min(2.0 * (attempt + 1), 20.0)
            logger.warning("Gnani network error on %s %s: %s. Retrying in %.1fs.", method, url, exc, delay)
            await asyncio.sleep(delay)
    if last_error:
        raise ProcessingError(ErrorCode.gnani_unavailable, retryable=True) from last_error
    raise ProcessingError(ErrorCode.gnani_unavailable, retryable=True)


def _raise_for_gnani(response: httpx.Response, action: str) -> None:
    if not response.is_error:
        return
    code = classify_gnani_http(response.status_code, response.text)
    logger.error("Gnani %s failed (%s): %s", action, response.status_code, response.text[:500])
    raise ProcessingError(code, retryable=code in {ErrorCode.gnani_rate_limit, ErrorCode.gnani_unavailable})



async def create_batch_job(
    *,
    language_code: str,
    options: TranscriptionOptions,
    source_url: str | None = None,
    audio_bytes: bytes | None = None,
    file_name: str = "audio",
    request_id: str | None = None,
) -> tuple[str, str]:
    """Create a Batch job.

    Prefers ``cloud_storage`` ingestion (no 10 MB byte ceiling, up to 4 hours)
    when a public/signed URL is available; otherwise falls back to a multipart
    upload.
    """
    settings = get_settings()
    request_id = request_id or _new_request_id()

    '''{
    "Authorization": f"Bearer {settings.gnani_api_key}",
    "Accept": "application/json"
    } '''
    headers = {**_headers(), "X-API-Request-ID": request_id}
    timeout = httpx.Timeout(180.0, connect=20.0)
    callback_url = None
    if settings.gnani_use_webhook and settings.gnani_webhook_base_url:
        callback_url = f"{settings.gnani_webhook_base_url.rstrip('/')}/api/webhooks/gnani"
        if settings.gnani_webhook_secret:
            callback_url = f"{callback_url}?secret={settings.gnani_webhook_secret}"

    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=timeout) as client:
        if settings.gnani_cloud_ingest and source_url and source_url.startswith(("http://", "https://")):
            body: dict = {"config": options.to_config(), "source": {"type": "cloud_storage", "auth": {"mode": "public"}, "paths": [source_url]}}
            if callback_url:
                body["callback_url"] = callback_url
            response = await _request_with_retry(client, "POST", BATCH_JOBS, headers=headers, json=body)
        else:
            if audio_bytes is None:
                raise ProcessingError(ErrorCode.storage_error, "Audio bytes were unavailable for upload.")
            content_type = MIME_TYPES.get(Path(file_name).suffix.lower(), "audio/wav")
            files = {
                "config": (None, json.dumps(options.to_config()), "application/json"),
                "files": (file_name, audio_bytes, content_type),
            }
            data = {"callback_url": callback_url} if callback_url else None
            response = await _request_with_retry(client, "POST", BATCH_JOBS, headers=headers, files=files, data=data)

        _raise_for_gnani(response, "create batch job")
        payload = response.json()
        job_id = payload.get("job_id")
        if not job_id:
            raise ProcessingError(ErrorCode.gnani_rejected, "The transcription service did not return a job id.")
        logger.info("Created Gnani Batch job %s (request_id=%s, cloud=%s)", job_id, request_id, bool(source_url and settings.gnani_cloud_ingest))
        return job_id, request_id


async def start_batch_job(job_id: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=60.0) as client:
        response = await _request_with_retry(
            client, "POST", f"{BATCH_JOBS}/{job_id}/start", headers=_headers()
        )
        _raise_for_gnani(response, "start batch job")


async def get_batch_job(job_id: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=60.0) as client:
        response = await _request_with_retry(client, "GET", f"{BATCH_JOBS}/{job_id}", headers=_headers())
        _raise_for_gnani(response, "get batch job")
        return response.json()


async def get_batch_job_files(job_id: str, status: str = "COMPLETED") -> list[dict]:
    """List per-file results. The API returns them under a ``data`` array."""
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=60.0) as client:
        response = await _request_with_retry(
            client,
            "GET",
            f"{BATCH_JOBS}/{job_id}/files",
            headers=_headers(),
            params={"status": status},
        )
        _raise_for_gnani(response, "get batch job files")
        payload = response.json()
        return payload.get("data") or payload.get("files") or []


async def download_transcript(transcript_url: str) -> dict:
    """Download the pre-signed transcript JSON (no API key required)."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(transcript_url)
        if response.is_error:
            raise ProcessingError(ErrorCode.gnani_unavailable, "Could not download the transcript from Gnani.")
        return response.json()


async def transcribe_rest(
    *,
    language_code: str,
    audio_bytes: bytes,
    file_name: str,
    use_itn: bool = True,
) -> str:
    """Synchronous REST transcription for short clips.

    The REST endpoint (unlike Batch) supports Inverse Text Normalization via
    ``format=transcribe``.
    """
    settings = get_settings()
    content_type = MIME_TYPES.get(Path(file_name).suffix.lower(), "audio/wav")
    # REST takes a single language code; if identification list was given, use the first.
    single_language = language_code.split(",")[0].strip() or "en-IN"
    data = {"language_code": single_language, "format": "transcribe" if use_itn else "verbatim"}
    files = {"audio_file": (file_name, audio_bytes, content_type)}
    timeout = httpx.Timeout(float(settings.gnani_rest_timeout_seconds), connect=20.0)
    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=timeout) as client:
        response = await _request_with_retry(
            client, "POST", REST_TRANSCRIBE, headers=_headers(), data=data, files=files
        )
        if response.status_code == 400 and "duration" in response.text.lower():
            raise ProcessingError(ErrorCode.file_too_large, "This clip is too long for the fast transcription path.")
        _raise_for_gnani(response, "rest transcription")
        return (response.json().get("transcript") or "").strip()


async def synthesize_speech(text: str, *, voice: str, language: str = "auto") -> bytes:
    """Generate speech with Gnani Timbre TTS and return the audio bytes (WAV)."""
    settings = get_settings()
    '''  This is a request body which we send to the Gnani Timber TSS API '''
    body = {
        "text": text[: settings.gnani_tts_max_chars],
        "voice": voice,
        "model": settings.gnani_tts_model,
        "language": language,
        "speed": 1.0, 
        # Request a WAV file that the summary player can play directly.
        "audio_config": {
            "sample_rate": 48000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    timeout = httpx.Timeout(120.0, connect=20.0)
    async with httpx.AsyncClient(base_url=settings.gnani_base_url.rstrip("/"), timeout=timeout) as client:
        response = await _request_with_retry(
            client, "POST", TTS_INFERENCE, headers={**_headers(), "Content-Type": "application/json"}, json=body
        )
        _raise_for_gnani(response, "tts synthesis")
        return response.content
