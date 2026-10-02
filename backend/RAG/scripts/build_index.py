"""
Step 2: data/processed/laws.jsonl -> data/index/embeddings.npy

    python -m scripts.build_index

The first run downloads the embedding model (BAAI/bge-m3, ~2.3GB) from Hugging Face.
BM25 (keyword) index is small, so it is built in memory when the retriever starts.
"""
from __future__ import annotations

import time

from legalrag.config import Config
from legalrag.store import build_embeddings, load_articles


def main() -> None:
    cfg = Config()
    articles = load_articles(cfg.processed_file)
    print(f"Embedding {len(articles)} articles with {cfg.embedding_model} ...")
    t = time.time()
    build_embeddings(cfg, articles)
    print(f"Done in {time.time() - t:.0f}s -> {cfg.index_dir}")


if __name__ == "__main__":
    main()
