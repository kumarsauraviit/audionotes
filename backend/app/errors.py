"""Domain errors that carry a stable, user-facing failure code."""

from __future__ import annotations

from app.models import ErrorCode


# Human-readable, non-technical copy for each failure code. The user should never
# have to read a stack trace to understand what happened.
ERROR_MESSAGES: dict[str, str] = {
    ErrorCode.unsupported_format.value: "That audio format isn’t supported. Try WAV, MP3, M4A, MP4, FLAC, OGG, OPUS, AAC, WEBM, or AMR.",
    ErrorCode.empty_file.value: "The audio file is empty. Nothing was uploaded.",
    ErrorCode.file_too_large.value: "This recording is larger than the upload limit.",
    ErrorCode.corrupt_audio.value: "This audio file appears to be corrupted or unreadable.",
    ErrorCode.silent_audio.value: "This recording looks silent — we couldn’t find any speech in it.",
    ErrorCode.no_speech.value: "We couldn’t detect any speech in this recording.",
    ErrorCode.storage_error.value: "We couldn’t store or read the audio file. Please try again.",
    ErrorCode.compression_failed.value: "We couldn’t prepare this audio for transcription.",
    ErrorCode.gnani_auth.value: "The transcription service rejected our credentials. Please try again later.",
    ErrorCode.gnani_rate_limit.value: "The transcription service is busy right now. Please retry in a moment.",
    ErrorCode.gnani_timeout.value: "Transcription took longer than expected and timed out. You can retry it.",
    ErrorCode.gnani_unavailable.value: "The transcription service is temporarily unavailable. Please retry shortly.",
    ErrorCode.gnani_rejected.value: "The transcription service couldn’t process this audio.",
    ErrorCode.summary_failed.value: "The transcript is ready, but we couldn’t generate a summary.",
    ErrorCode.internal_error.value: "Something went wrong while processing this recording.",
}


class ProcessingError(RuntimeError):
    """Raised inside the pipeline with a stable code and safe user message."""

    def __init__(self, code: ErrorCode | str, message: str | None = None, *, retryable: bool = False):
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.retryable = retryable
        self.user_message = message or ERROR_MESSAGES.get(self.code, ERROR_MESSAGES[ErrorCode.internal_error.value])
        super().__init__(self.user_message)


def classify_gnani_http(status_code: int, detail: str = "") -> ErrorCode:
    """Map a Gnani HTTP status to a user-facing failure code."""
    if status_code in (401, 403):
        return ErrorCode.gnani_auth
    if status_code == 429:
        return ErrorCode.gnani_rate_limit
    if status_code in (500, 502, 503, 504):
        return ErrorCode.gnani_unavailable
    if status_code == 400:
        text = (detail or "").lower()
        if "audio duration exceeds" in text or "too long" in text:
            return ErrorCode.file_too_large
        if "language" in text:
            return ErrorCode.gnani_rejected
        return ErrorCode.gnani_rejected
    return ErrorCode.gnani_rejected
