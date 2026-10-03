"""Conversational agent over a single recording.

The agent chooses transcript tools by replying with a small JSON protocol, which
we execute locally and feed back as text. This deliberately avoids the native
`functionCall` API: Gemini 3 requires replaying an encrypted `thought_signature`
on every function call, which the pinned `google-genai` SDK does not return, so
native tool calls are rejected. A JSON protocol works across every model and
keeps the loop transparent (tool events + citations).

Protocol the model is told to use:
    {"tool": "search_transcript", "args": {"query": "launch date"}}
    {"tool": "final", "answer": "..."}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from app.agent.tools import TOOL_FUNCTIONS, NoteContext
from app.config import get_settings
from app.gemini import generate_text

logger = logging.getLogger(__name__)

MAX_STEPS = 6
MAX_HISTORY_TURNS = 6
INLINE_TRANSCRIPT_CHARS = 6000
MAX_TOOL_RESULT_CHARS = 4000

TOOL_CATALOG = (
    "- search_transcript(args: {query, optional max_results}) -> matching moments with start_time/end_time/text.\n"
    "- read_transcript(args: {optional offset, optional max_chars}) -> a slice of the full transcript; "
    "the result includes next_offset to keep paging.\n"
    "- open_moment(args: {start_time, optional window_seconds}) -> the transcript around a timestamp.\n"
    "- list_chapters(args: {}) -> chapter titles with start times.\n"
    "- get_summary(args: {}) -> the recording's summary.\n"
    "- get_details(args: {}) -> duration, language, speakers, tags."
)

SYSTEM_TEMPLATE = """You are a conversational assistant for a single audio recording. Answer questions using \
tools that read and search the recording's transcript.

Reply with ONE JSON object and nothing else.

To use a tool, reply:
{{"tool": "<tool name>", "args": {{...}}}}

Available tools:
{catalog}

When you have enough information, reply:
{{"tool": "final", "answer": "your answer, with mm:ss timestamps for anything you reference"}}

Rules:
- Use the tools to find facts. Never invent details.
- Answer ONLY from the tool results (and the transcript below, if provided).
- If the tools return nothing relevant, say the recording does not appear to contain that.
- Keep the final answer concise and conversational.
"""


def _instructions(note: NoteContext) -> str:
    system = SYSTEM_TEMPLATE.format(catalog=TOOL_CATALOG)
    transcript = note.transcript or ""
    if transcript and len(transcript) <= INLINE_TRANSCRIPT_CHARS:
        system += (
            "\nThe recording is short, so its full transcript is included below. You may answer directly "
            "without calling a tool when the transcript already contains the answer.\n"
            f"\n--- FULL TRANSCRIPT ---\n{transcript}\n--- END FULL TRANSCRIPT ---\n"
        )
    else:
        duration = f", about {int(note.duration_seconds // 60)} minutes" if note.duration_seconds else ""
        system += (
            f"\nThe transcript is long ({len(transcript)} characters{duration}). Use search_transcript to find "
            "relevant parts, or read_transcript to page through it in chunks.\n"
        )
    return system


def _try_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _citations(name: str, result: dict) -> list[dict]:
    citations: list[dict] = []
    if name == "search_transcript":
        for match in result.get("matches", []):
            text = (match.get("text") or "").strip()
            if text:
                citations.append(
                    {
                        "content": text,
                        "start_time": match.get("start_time"),
                        "end_time": match.get("end_time"),
                        "speaker": match.get("speaker"),
                    }
                )
    elif name == "open_moment":
        for segment in result.get("segments", []):
            text = (segment.get("text") or "").strip()
            if text:
                citations.append(
                    {
                        "content": text,
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "speaker": None,
                    }
                )
    elif name == "read_transcript":
        text = (result.get("text") or "").strip()
        if text:
            citations.append(
                {
                    "content": text[:300],
                    "start_time": result.get("start_time"),
                    "end_time": result.get("end_time"),
                    "speaker": None,
                }
            )
    return citations


def _chunk_text(text: str, size: int = 140) -> Iterator[str]:
    words = text.split(" ")
    buffer = ""
    for word in words:
        if len(buffer) + len(word) + 1 > size and buffer:
            yield buffer + " "
            buffer = word
        else:
            buffer = f"{buffer} {word}".strip()
    if buffer:
        yield buffer


def iter_agent(note: NoteContext, question: str, history: list[dict] | None = None) -> Iterator[dict]:
    """Yield agent events: tool calls, sources, answer tokens, done."""
    if not get_settings().gemini_api_key:
        raise RuntimeError("Gemini is not configured. Add GEMINI_API_KEY to backend/.env.")

    clean_question = (question or "").strip()
    if not clean_question:
        raise ValueError("Question cannot be empty.")

    conversation: list[str] = [_instructions(note)]
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        prior_q = (turn.get("question") or "").strip()
        prior_a = (turn.get("answer") or "").strip()
        if prior_q and prior_a:
            conversation.append(f"Earlier question: {prior_q}\nEarlier answer: {prior_a}")
    conversation.append(f"Question: {clean_question}")

    scratchpad: list[str] = []
    sources: list[dict] = []
    seen: set[tuple] = set()

    def build_prompt() -> str:
        parts = list(conversation)
        if scratchpad:
            parts.append("TOOL RESULTS SO FAR:\n" + "\n".join(scratchpad))
        parts.append("Respond with one JSON object.")
        return "\n\n".join(parts)

    for _ in range(MAX_STEPS):
        raw = generate_text(build_prompt())
        data = _try_json(raw)

        if data and data.get("tool") == "final":
            answer = str(data.get("answer") or "").strip() or "I couldn't find an answer in this recording."
            yield {"type": "sources", "sources": sources}
            for piece in _chunk_text(answer):
                yield {"type": "token", "text": piece}
            yield {"type": "done"}
            return

        name = data.get("tool") if data else None
        if name and name in TOOL_FUNCTIONS:
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            yield {"type": "tool", "name": name, "args": args}
            try:
                result = TOOL_FUNCTIONS[name](note, **args)
            except TypeError as exc:
                result = {"error": f"Invalid arguments for {name}: {exc}"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tool %s failed", name)
                result = {"error": str(exc)}

            for citation in _citations(name, result if isinstance(result, dict) else {}):
                key = (citation["start_time"], citation["end_time"], citation["content"][:80])
                if key not in seen:
                    seen.add(key)
                    sources.append(citation)
            yield {"type": "tool_result", "name": name}
            scratchpad.append(f"[{name}] {json.dumps(result, ensure_ascii=False)[:MAX_TOOL_RESULT_CHARS]}")
            continue

        # Not a recognised tool call — treat the text as the model's answer.
        answer = (raw or "").strip() or "I couldn't find an answer in this recording."
        yield {"type": "sources", "sources": sources}
        for piece in _chunk_text(answer):
            yield {"type": "token", "text": piece}
        yield {"type": "done"}
        return

    yield {"type": "sources", "sources": sources}
    yield {"type": "token", "text": "I gathered some context but couldn't finish. Please rephrase the question."}
    yield {"type": "done"}


def answer_question(note: NoteContext, question: str, history: list[dict] | None = None) -> dict:
    """Run the agent and return the final answer plus the citations it used."""
    answer_parts: list[str] = []
    sources: list[dict] = []
    for event in iter_agent(note, question, history):
        if event["type"] == "token":
            answer_parts.append(event["text"])
        elif event["type"] == "sources":
            sources = event["sources"]
    return {"answer": "".join(answer_parts).strip(), "sources": sources}
