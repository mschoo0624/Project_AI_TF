"""
Step 2: data/processed/laws.jsonl -> data/index/embeddings.npy

    python -m scripts.build_index

The first run downloads the embedding model (BAAI/bge-m3, ~2.3GB) from Hugging Face.
BM25 (keyword) index is small, so it is built in memory when the retriever starts.
"""
from __future__ import annotations

import time
import argparse
import hashlib
import json
import numpy as np

from legalrag.config import Config
from legalrag.store import build_embeddings, load_articles, load_embeddings


def reusable(cfg, articles) -> bool:
    """Reuse only a readable index of the same content, model and article order."""
    try:
        info = json.loads((cfg.index_dir / 'index_info.json').read_text(encoding='utf-8'))
        if info.get('source_sha256') != hashlib.sha256(cfg.processed_file.read_bytes()).hexdigest():
            return False
        vectors = load_embeddings(cfg, articles)
        return vectors.ndim == 2 and vectors.shape[0] == len(articles) and vectors.shape[1] > 0 and bool(np.isfinite(vectors).all())
    except (OSError, ValueError, KeyError, RuntimeError, EOFError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--if-needed', action='store_true', help='Reuse an intact index when content and model match')
    args = parser.parse_args()
    cfg = Config()
    articles = load_articles(cfg.processed_file)
    if args.if_needed and reusable(cfg, articles):
        print(f'Index unchanged: reusing {cfg.index_dir}')
        return
    print(f"Embedding {len(articles)} articles with {cfg.embedding_model} ...")
    t = time.time()
    build_embeddings(cfg, articles)
    print(f"Done in {time.time() - t:.0f}s -> {cfg.index_dir}")


if __name__ == "__main__":
    main()
