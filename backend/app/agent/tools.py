"""Transcript tools for the conversational agent.

These are plain, testable functions over an immutable snapshot of a recording
(``NoteContext``). The agent's LLM decides which to call; the LLM never sees the
raw database, only what these return.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class NoteContext:
    """Detached snapshot of a note, safe to use after the DB session closes."""

    id: str
    filename: str
    duration_seconds: float | None = None
    language_code: str = "en-IN"
    detected_language: str | None = None
    transcript: str | None = None
    summary: str | None = None
    segments: list[dict] = field(default_factory=list)
    chapters: list[dict] = field(default_factory=list)
    speaker_labels: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_note(cls, note: Any) -> "NoteContext":
        return cls(
            id=note.id,
            filename=note.filename,
            duration_seconds=note.duration_seconds,
            language_code=note.language_code or "en-IN",
            detected_language=note.detected_language,
            transcript=note.transcript,
            summary=note.summary,
            segments=list(note.segments or []),
            chapters=list(note.chapters or []),
            speaker_labels=dict(note.speaker_labels or {}),
            tags=list(note.tags or []),
        )

    def speaker_label(self, speaker_id: Any) -> str | None:
        if speaker_id is None:
            return None
        return self.speaker_labels.get(str(speaker_id)) or f"Speaker {speaker_id}"


def _terms(query: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(query or "") if len(token) > 2]


def _result(segment: dict, ctx: NoteContext, score: float) -> dict:
    return {
        "start_time": float(segment.get("start_time") or 0.0),
        "end_time": float(segment.get("end_time") or 0.0),
        "text": (segment.get("text") or "").strip(),
        "speaker": ctx.speaker_label(segment.get("speaker_id")),
        "score": round(score, 2),
    }


def search_transcript(ctx: NoteContext, query: str, max_results: int = 6) -> dict:
    """Search the transcript for keywords; return matching moments with timestamps."""
    terms = _terms(query)
    phrase = (query or "").strip().lower()
    try:
        max_results = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        max_results = 6

    matches: list[tuple[float, int, dict]] = []
    for index, segment in enumerate(ctx.segments):
        text = (segment.get("text") or "")
        low = text.lower()
        if not low:
            continue
        score = 0.0
        if phrase and phrase in low:
            score += 5.0
        for term in terms:
            if term in low:
                score += 1.0 + 0.2 * low.count(term)
        if score > 0:
            matches.append((score, index, segment))

    matches.sort(key=lambda item: (-item[0], item[1]))
    results = [_result(segment, ctx, score) for score, _, segment in matches[:max_results]]

    if not results and ctx.transcript:
        # No timestamped segments (or none matched) — fall back to plain text search.
        sentences = re.split(r"(?<=[.!?])\s+", ctx.transcript)
        for sentence in sentences:
            low = sentence.lower()
            if phrase in low or any(term in low for term in terms):
                results.append(
                    {"start_time": None, "end_time": None, "text": sentence.strip(), "speaker": None, "score": 0.0}
                )
                if len(results) >= max_results:
                    break

    return {"query": query, "count": len(results), "matches": results}


def open_moment(ctx: NoteContext, start_time: float, window_seconds: float = 45) -> dict:
    """Read the transcript around a given start time (seconds)."""
    try:
        start = max(0.0, float(start_time))
        window = max(5.0, min(float(window_seconds or 45), 300.0))
    except (TypeError, ValueError):
        return {"error": "start_time must be a number of seconds."}

    end = start + window
    if not ctx.segments:
        return {"start_time": start, "end_time": end, "text": ctx.transcript or "", "segments": []}

    picked = [
        segment
        for segment in ctx.segments
        if float(segment.get("end_time") or 0.0) >= start and float(segment.get("start_time") or 0.0) <= end
    ]
    lines = []
    for segment in picked[:40]:
        stamp = _clock(segment.get("start_time"))
        speaker = ctx.speaker_label(segment.get("speaker_id"))
        prefix = f"[{stamp}]" + (f" {speaker}:" if speaker else "")
        lines.append(f"{prefix} {(segment.get('text') or '').strip()}")
    return {"start_time": start, "end_time": end, "text": "\n".join(lines), "segments": picked[:40]}


def list_chapters(ctx: NoteContext) -> dict:
    """List the topic chapters with their start times."""
    return {
        "chapters": [
            {
                "title": chapter.get("title"),
                "start_time": chapter.get("start_time"),
                "end_time": chapter.get("end_time"),
                "summary": chapter.get("summary"),
            }
            for chapter in ctx.chapters
        ]
    }


def get_summary(ctx: NoteContext) -> dict:
    """Get the recording's summary."""
    return {"summary": ctx.summary or ""}


def get_details(ctx: NoteContext) -> dict:
    """Get metadata about the recording: duration, language, speakers, tags."""
    speakers: dict[str, float] = {}
    for segment in ctx.segments:
        speaker = segment.get("speaker_id")
        if speaker is None:
            continue
        label = ctx.speaker_label(speaker)
        speakers[label] = round(
            speakers.get(label, 0.0) + max(0.0, float(segment.get("end_time") or 0) - float(segment.get("start_time") or 0)),
            1,
        )
    return {
        "filename": ctx.filename,
        "duration_seconds": ctx.duration_seconds,
        "language": ctx.detected_language or ctx.language_code,
        "speakers": speakers,
        "tags": ctx.tags,
        "chapter_count": len(ctx.chapters),
        "transcript_chars": len(ctx.transcript or ""),
    }


def _char_map(ctx: NoteContext) -> list[tuple[int, int, float, float]]:
    """Map character spans in the joined transcript to segment times."""
    mapping: list[tuple[int, int, float, float]] = []
    cursor = 0
    for segment in ctx.segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        if cursor:
            cursor += 1
        start = cursor
        cursor += len(text)
        mapping.append(
            (
                start,
                cursor,
                float(segment.get("start_time") or 0.0),
                float(segment.get("end_time") or 0.0),
            )
        )
    return mapping


def _time_at(mapping: list[tuple[int, int, float, float]], offset: int) -> tuple[float | None, float | None]:
    if not mapping:
        return None, None
    for start, end, start_time, end_time in mapping:
        if start <= offset <= end:
            return start_time, end_time
    if offset < mapping[0][0]:
        return mapping[0][2], mapping[0][3]
    return mapping[-1][2], mapping[-1][3]


def read_transcript(ctx: NoteContext, offset: int = 0, max_chars: int = 8000) -> dict:
    """Read a slice of the full transcript, for when it is too long to read at once.

    Returns the text plus the next offset to continue from.
    """
    full = ctx.transcript or ""
    total = len(full)
    try:
        offset = max(0, int(offset))
        max_chars = max(500, min(int(max_chars), 20000))
    except (TypeError, ValueError):
        offset, max_chars = 0, 8000

    if offset >= total:
        return {"text": "", "offset": total, "next_offset": None, "total_chars": total}

    chunk = full[offset : offset + max_chars]
    mapping = _char_map(ctx)
    start_time, _ = _time_at(mapping, offset)
    _, end_time = _time_at(mapping, offset + len(chunk))
    next_offset = offset + len(chunk)
    return {
        "text": chunk,
        "offset": offset,
        "next_offset": next_offset if next_offset < total else None,
        "total_chars": total,
        "start_time": start_time,
        "end_time": end_time,
    }


def _clock(value: Any) -> str:
    try:
        seconds = max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return "00:00"
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


# Registry the agent dispatches to.
TOOL_FUNCTIONS = {
    "search_transcript": search_transcript,
    "read_transcript": read_transcript,
    "open_moment": open_moment,
    "list_chapters": list_chapters,
    "get_summary": get_summary,
    "get_details": get_details,
}


def search_library(notes: list[NoteContext], query: str, limit: int = 8) -> list[dict]:
    """Lexically search across every recording's segments (no embeddings)."""
    terms = _terms(query)
    phrase = (query or "").strip().lower()
    hits: list[tuple[float, int, dict, NoteContext]] = []
    for ctx in notes:
        for index, segment in enumerate(ctx.segments):
            text = (segment.get("text") or "").strip()
            low = text.lower()
            if not low:
                continue
            score = 0.0
            if phrase and phrase in low:
                score += 5.0
            for term in terms:
                if term in low:
                    score += 1.0
            if score > 0:
                hits.append((score, index, segment, ctx))
    hits.sort(key=lambda item: -item[0])
    return [
        {
            "note_id": ctx.id,
            "filename": ctx.filename,
            "chunk_index": index,
            "content": (segment.get("text") or "").strip(),
            "score": round(score, 2),
            "start_time": float(segment.get("start_time") or 0.0) if segment.get("start_time") is not None else None,
            "end_time": float(segment.get("end_time") or 0.0) if segment.get("end_time") is not None else None,
        }
        for score, index, segment, ctx in hits[:limit]
    ]
