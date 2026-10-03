"""Derived, LLM-generated structure on top of a transcript.

Gnani gives us verbatim text and timestamps; Gemini turns that into the things a
user actually wants to act on: action items, decisions, dates, entities, and
topic chapters.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.gemini import generate_json

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You extract structured information from an audio transcript.

Return ONLY valid JSON with exactly these keys:
{{
  "action_items": ["..."],
  "decisions": ["..."],
  "dates": ["..."],
  "entities": {{"people": ["..."], "organizations": ["..."], "products": ["..."], "places": ["..."]}},
  "questions": ["..."]
}}

Rules:
- Use only information explicitly present in the transcript. Do not invent anything.
- Each list may be empty if nothing applies.
- Keep each item short (one clause).
- "dates" should include deadlines, meetings, and time references as spoken.

TRANSCRIPT:
{transcript}
"""

CHAPTER_PROMPT = """You are dividing a transcript into a few clear chapters.

Below is a numbered list of transcript segments. Return ONLY valid JSON:
{{"chapters": [{{"title": "Short title", "start_index": <segment number>, "summary": "one sentence"}}]}}

Rules:
- Produce 2 to 8 chapters, in order.
- "start_index" MUST be one of the segment numbers provided.
- The first chapter MUST start at segment 0.
- Base each chapter only on the segment text provided.

SEGMENTS:
{segments}
"""


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def extract_structured(transcript: str) -> dict | None:
    if not transcript or not transcript.strip():
        return None
    try:
        data = generate_json(EXTRACTION_PROMPT.format(transcript=transcript[:20000]))
    except Exception as exc:  # noqa: BLE001 - extraction is best-effort
        logger.warning("Structured extraction failed: %s", exc)
        return None

    entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    return {
        "action_items": _as_str_list(data.get("action_items")),
        "decisions": _as_str_list(data.get("decisions")),
        "dates": _as_str_list(data.get("dates")),
        "entities": {
            key: _as_str_list(entities.get(key))
            for key in ("people", "organizations", "products", "places")
        },
        "questions": _as_str_list(data.get("questions")),
    }


def build_chapters(segments: list[dict] | None, transcript: str | None = None) -> list[dict] | None:
    if not segments:
        return None

    # Compact, grounded segment listing: [index] mm:ss text
    lines: list[str] = []
    for index, segment in enumerate(segments):
        start = float(segment.get("start_time") or 0.0)
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        stamp = f"{int(start // 60):02d}:{int(start % 60):02d}"
        lines.append(f"[{index}] {stamp} {text}")
    if len(lines) < 2:
        return None

    # Keep the prompt bounded for very long transcripts.
    listing = "\n".join(lines[:400])
    try:
        data = generate_json(CHAPTER_PROMPT.format(segments=listing))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chapter generation failed: %s", exc)
        return None

    raw_chapters = data.get("chapters")
    if not isinstance(raw_chapters, list) or not raw_chapters:
        return None

    index_to_segment = {i: segments[i] for i in range(len(segments)) if segments[i].get("text")}

    chapter_starts: list[tuple[int, str, str]] = []
    for chapter in raw_chapters:
        if not isinstance(chapter, dict):
            continue
        try:
            start_index = int(chapter.get("start_index", 0))
        except (TypeError, ValueError):
            continue
        if start_index not in index_to_segment:
            # Snap to the nearest valid segment index.
            candidates = [i for i in index_to_segment if i <= start_index]
            if not candidates:
                continue
            start_index = max(candidates)
        title = str(chapter.get("title") or "Chapter").strip()[:120]
        summary = str(chapter.get("summary") or "").strip()[:400]
        chapter_starts.append((start_index, title, summary))

    if not chapter_starts:
        return None

    chapter_starts.sort(key=lambda item: item[0])
    if chapter_starts[0][0] != 0 and 0 in index_to_segment:
        first_title = chapter_starts[0][1]
        chapter_starts.insert(0, (0, first_title, ""))

    ordered_indices = sorted(index_to_segment)
    chapters: list[dict] = []
    for position, (start_index, title, summary) in enumerate(chapter_starts):
        start_segment = index_to_segment.get(start_index)
        if start_segment is None:
            continue
        if position + 1 < len(chapter_starts):
            next_index = chapter_starts[position + 1][0]
            preceding = [i for i in ordered_indices if i < next_index]
            end_segment_index = preceding[-1] if preceding else start_index
        else:
            end_segment_index = ordered_indices[-1]
        end_segment = index_to_segment.get(end_segment_index, start_segment)
        chapters.append(
            {
                "title": title,
                "start_time": float(start_segment.get("start_time") or 0.0),
                "end_time": float(end_segment.get("end_time") or start_segment.get("end_time") or 0.0),
                "summary": summary or None,
            }
        )
    return chapters or None
