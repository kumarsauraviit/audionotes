from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ProcessingStatus, SummaryStatus


class NoteUpdate(BaseModel):
    filename: str


class NoteOptionsUpdate(BaseModel):
    tags: list[str] | None = None
    speaker_labels: dict[str, str] | None = None


class SegmentOut(BaseModel):
    start_time: float
    end_time: float
    text: str
    speaker_id: int | None = None
    confidence: float | None = None


class TranscriptUpdate(BaseModel):
    transcript: str = Field(min_length=1)
    segments: list[SegmentOut] | None = None


class ProgressOut(BaseModel):
    stage: str | None = None
    percent: int | None = None
    message: str | None = None
    eta_seconds: int | None = None
    gnani_status: str | None = None


class ExtractionOut(BaseModel):
    action_items: list[str] = []
    decisions: list[str] = []
    dates: list[str] = []
    entities: dict[str, list[str]] = {}
    questions: list[str] = []


class ChapterOut(BaseModel):
    title: str
    start_time: float
    end_time: float
    summary: str | None = None


class NoteOut(BaseModel):
    id: str
    filename: str
    file_size: int
    language_code: str
    detected_language: str | None = None
    duration_seconds: float | None = None
    user_id: str | None = None
    status: ProcessingStatus
    transcript: str | None
    summary: str | None
    summary_status: SummaryStatus = SummaryStatus.pending
    segments: list[SegmentOut] | None = None
    extraction: dict | None = None
    chapters: list[ChapterOut] | None = None
    speaker_labels: dict[str, str] | None = None
    tags: list[str] | None = None
    transcription_engine: str | None = None
    summary_model: str | None = None
    # Processing telemetry
    stage: str | None = None
    progress_percent: int | None = None
    progress_message: str | None = None
    eta_seconds: int | None = None
    gnani_status: str | None = None
    # Options used for this note
    with_diarization: bool = False
    with_denoise: bool = False
    # Failure details
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    has_summary_audio: bool = False
    summary_audio_voice: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value):
        return value or None


class ConversationTurn(BaseModel):
    question: str = ""
    answer: str = ""


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=20)

    model_config = ConfigDict(str_strip_whitespace=True)


class SourceChunkOut(BaseModel):
    chunk_index: int = 0
    content: str
    score: float | None = None
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None


class QuestionResponse(BaseModel):
    note_id: str
    question: str
    answer: str
    sources: list[SourceChunkOut] = []


class GlossaryOut(BaseModel):
    glossary: list[str] = []
    default_language: str | None = None


class GlossaryUpdate(BaseModel):
    glossary: list[str] = Field(default_factory=list, max_length=100)
    default_language: str | None = Field(default=None, max_length=16)

    @field_validator("glossary")
    @classmethod
    def _validate_glossary(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for word in value:
            token = (word or "").strip()
            if not token:
                continue
            # Gnani requires one word of letters only (no spaces/digits/punctuation).
            if not token.isalpha():
                raise ValueError(f"'{token}' must be a single word of letters only.")
            if token not in cleaned:
                cleaned.append(token)
        if len(cleaned) > 100:
            raise ValueError("A glossary can hold at most 100 words.")
        return cleaned


class TTSRequest(BaseModel):
    voice: str | None = Field(default=None, max_length=64)


class LibrarySearchHit(BaseModel):
    note_id: str
    filename: str
    chunk_index: int
    content: str
    score: float | None = None
    start_time: float | None = None
    end_time: float | None = None


class LibrarySearchResponse(BaseModel):
    query: str
    hits: list[LibrarySearchHit] = []


class BulkUploadResult(BaseModel):
    filename: str
    note_id: str | None = None
    error: str | None = None


class BulkUploadResponse(BaseModel):
    accepted: list[BulkUploadResult] = []
    rejected: list[BulkUploadResult] = []


class UsageOut(BaseModel):
    total_notes: int
    total_audio_seconds: float
    total_audio_minutes: float
    total_transcript_chars: int
    total_tts_chars: int
    stt_estimate_inr: float
    tts_estimate_inr: float
    credits_estimate_inr: float
