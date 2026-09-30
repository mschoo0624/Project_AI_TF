"""Environment-driven settings for the STT service. Secrets never have defaults."""

from __future__ import annotations

import os

CLOVA_INVOKE_URL = os.getenv("CLOVA_INVOKE_URL")
CLOVA_SECRET_KEY = os.getenv("CLOVA_SECRET_KEY")

MAX_AUDIO_UPLOAD_BYTES = int(os.getenv("STT_MAX_AUDIO_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_AUDIO_DURATION_SECONDS = int(os.getenv("STT_MAX_AUDIO_DURATION_SECONDS", "600"))
ALLOWED_AUDIO_CONTENT_TYPES = frozenset(
    (os.getenv("STT_ALLOWED_AUDIO_CONTENT_TYPES") or "audio/mpeg,audio/wav,audio/x-m4a,audio/webm").split(",")
)


def require_clova_credentials() -> tuple[str, str]:
    """Fail fast with a clear error instead of sending empty CLOVA credentials."""
    if not CLOVA_INVOKE_URL or not CLOVA_SECRET_KEY:
        raise RuntimeError(
            "CLOVA_INVOKE_URL and CLOVA_SECRET_KEY environment variables must be set"
        )
    return CLOVA_INVOKE_URL, CLOVA_SECRET_KEY
