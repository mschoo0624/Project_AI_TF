"""Stub for a future on-device provider, so the CLOVA dependency can be replaced later."""

from __future__ import annotations

from stt.app.providers import SpeechToTextProvider
from stt.app.schemas.transcript import Transcript


class LocalWhisperProvider(SpeechToTextProvider):
    def transcribe(
        self, audio_bytes: bytes, content_type: str, *, language: str = "ko-KR"
    ) -> tuple[Transcript, dict]:
        raise NotImplementedError("Local faster-whisper provider is not implemented yet")
