"""Regression tests for Gnani summary-audio requests."""
import asyncio
from types import SimpleNamespace

from app import gnani_client


def test_synthesize_speech_sends_audio_config(monkeypatch):
    audio = b"RIFF\x00\x00\x00\x00WAVEfmt "
    captured = {}

    class FakeResponse:
        status_code = 200
        is_error = False
        content = audio

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_options"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return FakeResponse()

    monkeypatch.setattr(
        gnani_client,
        "get_settings",
        lambda: SimpleNamespace(
            gnani_api_key="test-key",
            gnani_tts_max_chars=3500,
            gnani_tts_model="timbre-v2.5",
            gnani_base_url="https://api.vachana.ai",
        ),
    )
    monkeypatch.setattr(gnani_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(gnani_client.synthesize_speech("Summary text", voice="Kaveri", language="en-IN"))

    assert result == audio
    assert captured["method"] == "POST"
    assert captured["url"] == gnani_client.TTS_INFERENCE
    assert captured["json"]["audio_config"] == {
        "sample_rate": 48000,
        "num_channels": 1,
        "sample_width": 2,
        "encoding": "linear_pcm",
        "container": "wav",
    }
    assert not any("audio_config" in key and key != "audio_config" for key in captured["json"])
