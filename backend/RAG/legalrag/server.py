"""
Web server (FastAPI).

    python -m uvicorn legalrag.server:app --port 8000
    -> open http://127.0.0.1:8000

Endpoints
    GET  /                 web UI (ui/index.html)
    GET  /api/status       is the model loaded? is an LLM configured?
    POST /api/search       {"question": "...", "top_k": 6}  -> retrieved articles only
    POST /api/ask          {"question": "...", "top_k": 6}  -> answer + articles (JSON)
    POST /api/ask/stream   same, streamed as NDJSON lines: {"type":"hits"...} then {"type":"token"...}
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from legalrag.pipeline import RagPipeline
from legalrag.utils import get_logger

logger = get_logger(__name__)
UI_FILE = Path(__file__).resolve().parent.parent / "ui" / "index.html"

app = FastAPI(title="예비군 법령 챗봇")
_rag: Optional[RagPipeline] = None
_load_error: Optional[str] = None


def _load() -> None:
    global _rag, _load_error
    try:
        _rag = RagPipeline()
    except Exception as e:  # shown in the UI instead of crashing the server
        logger.exception("pipeline load failed")
        _load_error = f"{type(e).__name__}: {e}"


@app.on_event("startup")
def startup() -> None:
    # load models in the background so the page opens immediately
    threading.Thread(target=_load, daemon=True).start()


def _pipeline() -> RagPipeline:
    if _load_error:
        raise HTTPException(500, _load_error)
    if _rag is None:
        raise HTTPException(503, "모델을 불러오는 중입니다. 잠시 후 다시 시도하세요.")
    return _rag


class Query(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(UI_FILE)


@app.get("/api/status")
def status():
    info = {"ready": _rag is not None, "error": _load_error}
    if _rag is not None:
        cfg = _rag.cfg
        info.update(
            llm=cfg.llm_model if _rag.llm else None,
            articles=len(_rag.retriever.articles),
            laws=_rag.retriever.law_names,
            reference_date=_rag.retriever.reference_date(),
        )
    return info


@app.post("/api/search")
def search(q: Query):
    hits = _pipeline().search(q.question, q.top_k)
    return {"question": q.question, "hits": [h.to_dict() for h in hits]}


@app.post("/api/ask")
def ask(q: Query):
    return _pipeline().ask(q.question, q.top_k)


@app.post("/api/ask/stream")
def ask_stream(q: Query):
    rag = _pipeline()

    def gen():
        try:
            for event in rag.ask_stream(q.question, q.top_k):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as e:
            logger.exception("ask_stream failed")
            yield json.dumps({"type": "error", "text": f"{type(e).__name__}: {e}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
