"""Lightweight audio preflight using the ffmpeg binary bundled with imageio-ffmpeg.

We validate the file (so a corrupt upload fails fast, before we spend a Gnani job)
and read its duration (so progress can be estimated).
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioProbeError(ValueError):
    """The uploaded bytes are not a readable audio file."""


@dataclass
class AudioMetadata:
    duration_seconds: float | None
    format_name: str | None
    codec: str | None
    channels: int | None
    has_audio_stream: bool


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:\s*([a-zA-Z0-9_]+)")
_CHANNELS_RE = re.compile(r"Audio:[^,]+(?:,[^,]+)*,\s*(\d+)\s*channels")


def _ffmpeg_exe() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on environment
        raise AudioProbeError("Audio inspection is unavailable because ffmpeg is not installed.") from exc


def probe_audio(data: bytes, filename: str) -> AudioMetadata:
    if not data:
        raise AudioProbeError("The uploaded audio file is empty.")

    suffix = Path(filename).suffix.lower() or ".audio"
    with tempfile.TemporaryDirectory(prefix="audio-notes-probe-") as temp_dir:
        input_path = Path(temp_dir) / f"source{suffix}"
        input_path.write_bytes(data)
        try:
            completed = subprocess.run(
                [_ffmpeg_exe(), "-hide_banner", "-i", str(input_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioProbeError("Timed out while reading this audio file.") from exc

    stderr = completed.stderr or ""
    duration_match = _DURATION_RE.search(stderr)
    stream_match = _AUDIO_STREAM_RE.search(stderr)
    channels_match = _CHANNELS_RE.search(stderr)

    duration_seconds: float | None = None
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    if stream_match is None:
        raise AudioProbeError("No audio stream could be found in this file.")

    metadata = AudioMetadata(
        duration_seconds=duration_seconds,
        format_name=None,
        codec=stream_match.group(1),
        channels=int(channels_match.group(1)) if channels_match else None,
        has_audio_stream=True,
    )
    logger.info(
        "Probed %s: codec=%s channels=%s duration=%s",
        filename,
        metadata.codec,
        metadata.channels,
        metadata.duration_seconds,
    )
    return metadata

