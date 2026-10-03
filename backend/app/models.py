import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcessingStatus(str, enum.Enum):
    queued = "queued"
    transcribing = "transcribing"
    summarizing = "summarizing"
    indexing = "indexing"
    complete = "complete"
    # Finished, but one non-fatal step (usually the summary) did not succeed.
    complete_with_warnings = "complete_with_warnings"
    failed = "failed"


class SummaryStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    failed = "failed"
    skipped = "skipped"


# Stable, machine-readable failure reasons surfaced to the user.
class ErrorCode(str, enum.Enum):
    unsupported_format = "unsupported_format"
    empty_file = "empty_file"
    file_too_large = "file_too_large"
    corrupt_audio = "corrupt_audio"
    silent_audio = "silent_audio"
    no_speech = "no_speech"
    storage_error = "storage_error"
    compression_failed = "compression_failed"
    gnani_auth = "gnani_auth"
    gnani_rate_limit = "gnani_rate_limit"
    gnani_timeout = "gnani_timeout"
    gnani_unavailable = "gnani_unavailable"
    gnani_rejected = "gnani_rejected"
    summary_failed = "summary_failed"
    internal_error = "internal_error"


class AudioNote(Base):
    __tablename__ = "audio_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    # Language requested by the user; may be a comma-separated identification list.
    language_code: Mapped[str] = mapped_column(String(32), default="en-IN", nullable=False)
    # Language Gnani resolved and actually transcribed in (single code).
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, native_enum=False), default=ProcessingStatus.queued, nullable=False
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_status: Mapped[SummaryStatus] = mapped_column(
        Enum(SummaryStatus, native_enum=False), default=SummaryStatus.pending, nullable=False
    )
    # Timestamped transcript segments from Gnani: [{start_time, end_time, text, speaker_id, confidence}]
    segments: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    # Structured extraction: {action_items: [], decisions: [], dates: [], entities: {}}
    extraction: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    # Topic chapters derived from segments: [{title, start_time, end_time, summary}]
    chapters: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    # Speaker id -> display label, e.g. {"1": "Interviewer", "2": "Guest"}
    speaker_labels: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    transcription_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Processing / progress telemetry (shown to the user) ---
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gnani_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Gnani correlation + request options ---
    gnani_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gnani_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    with_diarization: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    with_denoise: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bias_list: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    bias_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Summary read-aloud audio (object URL), generated with Gnani Timbre TTS.
    summary_audio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary_audio_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    @property
    def has_summary_audio(self) -> bool:
        return bool(self.summary_audio_path)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Reusable custom vocabulary (Gnani bias_list) applied to every new job.
    glossary: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    default_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (Index("ix_email_verification_tokens_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
