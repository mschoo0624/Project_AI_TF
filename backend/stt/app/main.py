"""STT voice-to-task service entry point (Phase 1: upload + CLOVA transcription)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stt.app.api.voice import router as voice_router

app = FastAPI(title="Project AI TF STT Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(voice_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Project AI TF STT service is running"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
