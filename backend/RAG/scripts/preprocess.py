"""
Step 1: data/raw/*.doc (law.go.kr RTF exports) -> data/processed/laws.jsonl

    python -m scripts.preprocess
    python -m scripts.preprocess --dump-text     # also write the extracted plain text for inspection
"""
from __future__ import annotations

import argparse
from collections import Counter

from legalrag.config import Config
from legalrag.parser import parse_law_file
from legalrag.rtf import read_rtf
from legalrag.store import save_articles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-text", action="store_true", help="save extracted text to data/processed/text/")
    args = ap.parse_args()

    cfg = Config()
    files = sorted(p for p in cfg.raw_dir.iterdir() if p.suffix.lower() in (".doc", ".rtf", ".txt"))
    if not files:
        print(f"No .doc/.rtf/.txt files in {cfg.raw_dir}")
        return 1

    articles = []
    for path in files:
        arts = parse_law_file(path)
        a = arts[0]
        n_add = sum(x.is_addendum for x in arts)
        print(f"{path.name}\n   -> {a.law_name} ({a.law_type} {a.promulgation_no}, 시행 {a.effective_date}): "
              f"{len(arts) - n_add} articles + {n_add} addenda")
        articles.extend(arts)
        if args.dump_text and path.suffix.lower() in (".doc", ".rtf"):
            out = cfg.processed_file.parent / "text" / (path.stem + ".txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(read_rtf(path), encoding="utf-8")

    dup = [k for k, v in Counter(a.id for a in articles).items() if v > 1]
    if dup:
        raise SystemExit(f"Duplicate article ids (same law version twice in data/raw?): {dup[:5]}")

    save_articles(cfg.processed_file, articles)
    print(f"\nSaved {len(articles)} records -> {cfg.processed_file}")
    print(f"Cross-references found: {sum(len(a.refs) for a in articles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
