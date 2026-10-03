import re
import subprocess
import tempfile
from pathlib import Path


MAX_GNANI_AUDIO_BYTES = 9_500 * 1024
TARGET_COMPRESSED_BYTES = int(9.2 * 1024 * 1024)
MIN_OPUS_BITRATE = 16_000
MAX_OPUS_BITRATE = 64_000


class AudioCompressionError(ValueError):
    """The input cannot be compressed to a useful size for transcription."""


def compress_for_transcription(data: bytes, filename: str) -> tuple[bytes, str, str]:
    """Encode speech as mono Opus/WebM at a bitrate sized for Gnani's upload cap."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ffmpeg = get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("Audio compression is unavailable. Install backend requirements and restart the API.") from exc

    suffix = Path(filename).suffix.lower() or ".audio"
    with tempfile.TemporaryDirectory(prefix="audio-notes-compress-") as temp_dir:
        input_path = Path(temp_dir) / f"source{suffix}"
        output_path = Path(temp_dir) / "compressed.webm"
        input_path.write_bytes(data)

        probe = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(input_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
        if not match:
            raise AudioCompressionError("Could not read this audio file’s duration to prepare a transcription-quality compressed copy.")
        hours, minutes, seconds = match.groups()
        duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if duration_seconds <= 0:
            raise AudioCompressionError("The selected audio has no usable duration.")

        bitrate = min(MAX_OPUS_BITRATE, int(TARGET_COMPRESSED_BYTES * 8 / duration_seconds))
        if bitrate < MIN_OPUS_BITRATE:
            raise AudioCompressionError("This recording is too long to fit Gnani’s limit at a useful speech bitrate. Please shorten it and try again.")

        conversion = subprocess.run(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(input_path), "-map_metadata", "-1", "-vn", "-ac", "1",
                "-ar", "16000", "-c:a", "libopus", "-b:a", str(bitrate),
                "-vbr", "on", "-application", "voip", "-f", "webm", str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=30 * 60,
            check=False,
        )
        if conversion.returncode != 0 or not output_path.exists():
            detail = conversion.stderr.strip()
            if "Unknown encoder" in detail:
                raise RuntimeError("The bundled FFmpeg build does not include the Opus encoder.")
            raise AudioCompressionError("Could not compress this audio. The original file was not changed.")

        compressed = output_path.read_bytes()
        if not compressed:
            raise AudioCompressionError("Audio compression produced an empty file.")
        if len(compressed) > MAX_GNANI_AUDIO_BYTES:
            raise AudioCompressionError("The compressed copy is still too large for Gnani. Please shorten the recording or choose a smaller file.")

    compressed_name = f"{Path(filename).stem}_compressed.webm"
    return compressed, compressed_name, "audio/webm"
