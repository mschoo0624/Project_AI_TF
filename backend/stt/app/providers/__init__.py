"""Abstract STT provider interface so callers never depend on a specific vendor."""

from __future__ import annotations

from abc import ABC, abstractmethod

from stt.app.schemas.transcript import Transcript


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(
        self, audio_bytes: bytes, content_type: str, *, language: str = "ko-KR"
    ) -> tuple[Transcript, dict]:
        """Return the normalized transcript plus the raw provider response for audit."""
