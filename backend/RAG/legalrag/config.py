"""
All settings in one place. Every value can be overridden with an environment variable
(e.g. `set RAG_TOP_K=8` on Windows cmd, `$env:RAG_TOP_K=8` in PowerShell).
Values can also be written once in a `.env` file in the project root (KEY=value per line);
real environment variables take precedence over `.env`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default):
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    if isinstance(default, bool):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return type(default)(val)


@dataclass
class Config:
    # ---- paths ----
    raw_dir: Path = DATA_DIR / "raw"                       # 원본 .doc(RTF) 파일
    processed_file: Path = DATA_DIR / "processed" / "laws.jsonl"
    index_dir: Path = DATA_DIR / "index"

    # ---- embedding (dense retrieval) ----
    # bge-m3: multilingual model with strong Korean performance
    embedding_model: str = field(default_factory=lambda: _env("RAG_EMBEDDING_MODEL", "BAAI/bge-m3"))

    # ---- retrieval ----
    top_k: int = field(default_factory=lambda: _env("RAG_TOP_K", 6))            # 최종 LLM에 넘길 조문 수
    candidates: int = field(default_factory=lambda: _env("RAG_CANDIDATES", 30))  # 각 검색기에서 가져올 후보 수
    dense_weight: float = 0.6
    bm25_weight: float = 0.4
    rrf_k: int = 60
    # add articles referenced by / referencing the top hits (법 ↔ 시행령 ↔ 시행규칙)
    expand_references: bool = field(default_factory=lambda: _env("RAG_EXPAND_REFS", True))
    max_reference_hits: int = 4
    # include 부칙 (addenda) articles in search results
    include_addenda: bool = field(default_factory=lambda: _env("RAG_INCLUDE_ADDENDA", True))

    # ---- optional cross-encoder reranker (slower on CPU, more accurate) ----
    enable_rerank: bool = field(default_factory=lambda: _env("RAG_RERANK", False))
    rerank_model: str = field(default_factory=lambda: _env("RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"))

    # ---- LLM (any OpenAI-compatible API: OpenAI, Ollama, vLLM, ...) ----
    llm_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini"))
    llm_temperature: float = field(default_factory=lambda: _env("RAG_TEMPERATURE", 0.2))
    llm_timeout: float = field(default_factory=lambda: _env("RAG_LLM_TIMEOUT", 120.0))

    # 기준일 (YYYY-MM-DD). Empty = today. Decides which law version is "현행" vs "시행 예정".
    reference_date: str = field(default_factory=lambda: _env("RAG_REFERENCE_DATE", ""))

    @property
    def llm_enabled(self) -> bool:
        # Ollama etc. need no real key, only a base URL
        return bool(self.llm_api_key or self.llm_base_url)
