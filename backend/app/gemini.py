"""Shared Gemini helpers with model fallback and per-model cooldowns.

Used by summaries, structured extraction, and the transcript agent. A model that
returns 429 (quota) or 404 (retired) is put on a cooldown so we stop retrying it
and fall through to another model instead. Free-tier quotas are per-model, so
spreading requests across a few models meaningfully increases throughput.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

from google import genai

from app.config import get_settings

logger = logging.getLogger(__name__)

# Only currently-available models, cheapest/highest-quota first. Do NOT add
# retired families (e.g. 2.5-flash returns 404 for new accounts). Each entry has
# its own free-tier daily quota, so lite models are preferred.
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]

_MAX_COOLDOWN_SECONDS = 3600.0
_RETIRED_COOLDOWN_SECONDS = 24 * 3600.0

_cooldowns: dict[str, float] = {}
_cooldown_lock = threading.Lock()


class GeminiNotConfigured(RuntimeError):
    pass


def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiNotConfigured("Gemini is not configured. Add GEMINI_API_KEY to backend/.env.")
    return genai.Client(api_key=settings.gemini_api_key)


def _ordered_models() -> list[str]:
    preferred = get_settings().gemini_model
    ordered = [preferred] + [model for model in FALLBACK_MODELS if model != preferred]
    now = time.time()
    available = [model for model in ordered if _cooldowns.get(model, 0.0) <= now]
    # If everything is cooling down, still try in order rather than failing fast.
    return available or ordered


def _set_cooldown(model: str, seconds: float) -> None:
    with _cooldown_lock:
        _cooldowns[model] = time.time() + seconds
    logger.warning("Model %s cooling down for %.0fs", model, seconds)


def _handle_model_error(model: str, exc: Exception) -> None:
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text or "quota" in text.lower():
        match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", text)
        delay = float(match.group(1)) if match else 120.0
        _set_cooldown(model, min(max(delay, 60.0), _MAX_COOLDOWN_SECONDS))
    elif "NOT_FOUND" in text or "404" in text or "no longer available" in text:
        _set_cooldown(model, _RETIRED_COOLDOWN_SECONDS)
    else:
        logger.warning("Gemini model %s failed: %s", model, exc)


def generate_content(contents: Any, config: Any | None = None) -> tuple[Any, str]:
    """Generate content, trying each available model. Returns (response, model)."""
    client = _client()
    last_error: Exception | None = None
    for model in _ordered_models():
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            return response, model
        except Exception as exc:  # noqa: BLE001 - provider errors are varied
            last_error = exc
            _handle_model_error(model, exc)
    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def generate_text(contents: Any) -> str:
    response, _ = generate_content(contents)
    return (response.text or "").strip()


def generate_text_with_model(contents: Any) -> tuple[str, str]:
    response, model = generate_content(contents)
    return (response.text or "").strip(), model


def _extract_json(raw: str) -> dict:
    """Parse JSON from a model response, tolerating ```json fences."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def generate_json(prompt: str) -> dict:
    return _extract_json(generate_text(prompt))
