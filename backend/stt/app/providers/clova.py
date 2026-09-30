"""CLOVA Speech provider (sync, short-clip path). Long-clip async/callback is not implemented yet."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import httpx

from stt.app.config import require_clova_credentials
from stt.app.providers import SpeechToTextProvider
from stt.app.schemas.transcript import Transcript, TranscriptSegment


class ClovaSpeechProvider(SpeechToTextProvider):
    def __init__(self, *, boosting_vocabulary: list[str] | None = None, timeout_seconds: float = 60.0) -> None:
        self._boosting_vocabulary = boosting_vocabulary or []
        self._timeout_seconds = timeout_seconds

    def transcribe(
        self, audio_bytes: bytes, content_type: str, *, language: str = "ko-KR"
    ) -> tuple[Transcript, dict]:
        invoke_url, secret_key = require_clova_credentials()
        params: dict[str, object] = {
            "language": language,
            "completion": "sync",
            "wordAlignment": True,
            "fullText": True,
        }
        if self._boosting_vocabulary:
            params["boostings"] = [{"words": word} for word in self._boosting_vocabulary]

        response = httpx.post(
            f"{invoke_url}/recognizer/upload",
            headers={"X-CLOVASPEECH-API-KEY": secret_key},
            files={"media": ("audio", audio_bytes, content_type)},
            data={"params": json.dumps(params)},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        raw = response.json()
        return self._normalize(raw, language), raw

    def _normalize(self, raw: dict, language: str) -> Transcript:
        # Field names are provisional; confirm against a real CLOVA response before production use.
        segments = [
            TranscriptSegment(
                start_ms=int(segment.get("start", 0)),
                end_ms=int(segment.get("end", 0)),
                speaker=segment.get("speaker", {}).get("name") if isinstance(segment.get("speaker"), dict) else segment.get("speaker"),
                text=segment.get("text", ""),
                confidence=float(segment.get("confidence", 0.0)),
            )
            for segment in raw.get("segments", [])
        ]
        return Transcript(
            transcript_id=str(uuid.uuid4()),
            language=language,
            duration_sec=float(raw.get("duration", 0)) / 1000,
            full_text=raw.get("text", ""),
            segments=segments,
            provider="clova_speech",
            created_at=datetime.now(timezone.utc),
        )
