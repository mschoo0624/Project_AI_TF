"""
Loading/saving the processed corpus and the vector index.

data/processed/laws.jsonl   one JSON line per article (output of scripts/preprocess.py)
data/index/embeddings.npy   one normalized vector per article (output of scripts/build_index.py)
data/index/index_info.json  which model built the vectors + article ids in the same order
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import numpy as np

from legalrag.config import Config
from legalrag.parser import Article

_ANNOTATION_RE = re.compile(r"<(?:개정|신설|삭제|본조신설|전문개정|제목개정|종전)[^>]*>|\[(?:전문개정|본조신설|제목개정|종전|시행일)[^\]]*\]|\[[^\]]*이동[^\]]*\]")


def save_articles(path: Path, articles: List[Article]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for a in articles:
            f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")


def load_articles(path: Path) -> List[Article]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python -m scripts.preprocess")
    with path.open(encoding="utf-8") as f:
        return [Article(**json.loads(line)) for line in f if line.strip()]


def clean_text(text: str) -> str:
    """Remove amendment history like '<개정 2016. 5. 29.>' / '[전문개정 2010. 1. 25.]' (noise for search)."""
    text = _ANNOTATION_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def search_text(a: Article) -> str:
    """The text that is embedded / keyword-indexed for one article."""
    where = " ".join(x for x in (a.chapter, a.section) if x)
    return f"{a.display_name}\n{where}\n{clean_text(a.text)}".strip()


def load_embedding_model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device="cpu" if not _has_cuda() else "cuda")


def _has_cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def build_embeddings(cfg: Config, articles: List[Article]) -> None:
    model = load_embedding_model(cfg.embedding_model)
    texts = [search_text(a) for a in articles]
    vecs = model.encode(texts, batch_size=8, normalize_embeddings=True, show_progress_bar=True)
    cfg.index_dir.mkdir(parents=True, exist_ok=True)
    np.save(cfg.index_dir / "embeddings.npy", np.asarray(vecs, dtype="float32"))
    info = {"embedding_model": cfg.embedding_model, "ids": [a.id for a in articles]}
    (cfg.index_dir / "index_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")


def load_embeddings(cfg: Config, articles: List[Article]) -> np.ndarray:
    emb_path = cfg.index_dir / "embeddings.npy"
    info_path = cfg.index_dir / "index_info.json"
    if not emb_path.exists() or not info_path.exists():
        raise FileNotFoundError(f"Vector index not found in {cfg.index_dir}. Run: python -m scripts.build_index")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    if info["ids"] != [a.id for a in articles]:
        raise RuntimeError("Index is out of date with laws.jsonl. Re-run: python -m scripts.build_index")
    if info["embedding_model"] != cfg.embedding_model:
        raise RuntimeError(
            f"Index was built with {info['embedding_model']} but config uses {cfg.embedding_model}. "
            "Re-run: python -m scripts.build_index"
        )
    return np.load(emb_path)
