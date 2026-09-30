"""Voice upload/transcription routes. Persistence is not wired up yet (no DB layer in Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from stt.app.config import ALLOWED_AUDIO_CONTENT_TYPES, MAX_AUDIO_UPLOAD_BYTES
from stt.app.providers.clova import ClovaSpeechProvider
from stt.app.schemas.transcript import Transcript

router = APIRouter(prefix="/voice", tags=["voice"])
_provider = ClovaSpeechProvider()


@router.post("/transcriptions", response_model=Transcript, status_code=status.HTTP_201_CREATED)
async def create_transcription(file: UploadFile = File(...)) -> Transcript:
    if file.content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type: {file.content_type}",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio file exceeds the maximum upload size",
        )

    transcript, _raw_response = _provider.transcribe(audio_bytes, file.content_type)
    return transcript
