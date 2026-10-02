"""
Ask questions from the terminal.

    python -m scripts.ask "예비군 훈련은 1년에 며칠까지 받나요?"
    python -m scripts.ask --search-only "직장 보장"   # only show retrieved articles
"""
from __future__ import annotations

import argparse
import sys

from legalrag.pipeline import RagPipeline


def show(rag: RagPipeline, question: str, search_only: bool, top_k: int | None) -> None:
    if search_only:
        hits = [h.to_dict() for h in rag.search(question, top_k)]
    else:
        result = rag.ask(question, top_k)
        hits = result["hits"]
        print("\n" + "=" * 70 + "\n" + result["answer"] + "\n" + "=" * 70)
    print("\n[검색된 조문]")
    for n, h in enumerate(hits, 1):
        print(f" {n:>2}. {h['title']}  [{h['status']}, {h['via']}, score={h['score']:.3f}]")
    if search_only:
        for n, h in enumerate(hits, 1):
            print(f"\n--- [{n}] {h['title']} ({h['promulgation_no']}, 시행 {h['effective_date']})\n{h['text']}")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")  # Korean output on Windows consoles
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--top-k", type=int, default=None)
    args = ap.parse_args()

    rag = RagPipeline()
    if args.question:
        show(rag, " ".join(args.question), args.search_only, args.top_k)
        return
    print("질문을 입력하세요 (종료: 빈 줄 또는 Ctrl+C)")
    while True:
        try:
            q = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        show(rag, q, args.search_only, args.top_k)


if __name__ == "__main__":
    main()
