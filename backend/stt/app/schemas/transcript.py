"""Normalized transcript schema, independent of any single STT provider's response shape."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    start_ms: int
    end_ms: int
    speaker: str | None = None
    text: str
    confidence: float


class Transcript(BaseModel):
    transcript_id: str
    language: str
    duration_sec: float
    full_text: str
    segments: list[TranscriptSegment]
    provider: str
    created_at: datetime
