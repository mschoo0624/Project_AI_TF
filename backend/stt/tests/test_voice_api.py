"""Tests for the voice upload endpoint using a monkeypatched provider (no live CLOVA calls)."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from stt.app import main
from stt.app.api import voice
from stt.app.schemas.transcript import Transcript


def _stub_transcript() -> Transcript:
    return Transcript(
        transcript_id="stub-id",
        language="ko-KR",
        duration_sec=1.5,
        full_text="테스트 발화",
        segments=[],
        provider="clova_speech",
        created_at=datetime.now(timezone.utc),
    )


def test_rejects_unsupported_content_type():
    client = TestClient(main.app)
    response = client.post(
        "/voice/transcriptions",
        files={"file": ("clip.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 415


def test_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(voice, "MAX_AUDIO_UPLOAD_BYTES", 4)
    client = TestClient(main.app)
    response = client.post(
        "/voice/transcriptions",
        files={"file": ("clip.wav", b"12345678", "audio/wav")},
    )
    assert response.status_code == 413


def test_returns_normalized_transcript(monkeypatch):
    monkeypatch.setattr(
        voice._provider, "transcribe", lambda audio_bytes, content_type, **kwargs: (_stub_transcript(), {"raw": True})
    )
    client = TestClient(main.app)
    response = client.post(
        "/voice/transcriptions",
        files={"file": ("clip.wav", b"12345678", "audio/wav")},
    )
    assert response.status_code == 201
    assert response.json()["transcript_id"] == "stub-id"
