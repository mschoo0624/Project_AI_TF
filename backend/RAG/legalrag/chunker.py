"""
Article (조문) -> passages (항 단위).

Retrieval works on passages instead of whole articles so that the LLM only receives the
항 (paragraphs) that are relevant to the question, not the entire 조문 with every 호.

    제6조(예비군의 편성)            <- article line (title is added to every passage for context)
    ① 예비군은 ...                  <- passage "제1항"
    1. ...  2. ...                  <- 호/목 lines stay with the 항 they belong to
    ② ...                          <- passage "제2항"

Articles that are short, or have no 항 markers, stay a single passage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from .parser import ARTICLE_RE, Article

# ①..⑳ (U+2460-2473), ㉑..㉟ (U+3251-325F), ㊱..㊿ (U+32B1-32BF)
_CIRCLED = [chr(c) for c in range(0x2460, 0x2474)] + \
           [chr(c) for c in range(0x3251, 0x3260)] + \
           [chr(c) for c in range(0x32B1, 0x32C0)]
_PARA_NO = {ch: i + 1 for i, ch in enumerate(_CIRCLED)}
PARA_RE = re.compile("^([" + "".join(_CIRCLED) + "])")

MIN_SPLIT_CHARS = 350   # articles shorter than this are not split


@dataclass
class Chunk:
    article_idx: int
    order: int          # position inside the article (0-based)
    label: str          # "" (whole article) / "제2항" / "전문"
    text: str           # passage text (starts with the ① marker for a 항)
    is_whole: bool      # True when the article was not split
    total: int = 1      # number of passages in the article


def _split_paragraphs(a: Article) -> List[Tuple[str, str]]:
    """Split into 항. A single ("", text) means 'not split'."""
    lines = [ln for ln in a.text.splitlines() if ln.strip()]
    if not lines:
        return [("", a.text)]

    # The first line is "제N조(제목) 본문..."; drop the head so a leading "① ..." is detected.
    first = lines[0]
    m = ARTICLE_RE.match(first)
    body_lines = list(lines[1:])
    if m and not a.is_addendum:
        body = (m.group("body") or "").strip()
        if body:
            body_lines.insert(0, body)
    else:
        body_lines.insert(0, first)

    if len(a.text) < MIN_SPLIT_CHARS:
        return [("", a.text)]

    paras: List[List[str]] = []
    labels: List[str] = []
    for ln in body_lines:
        pm = PARA_RE.match(ln.strip())
        if pm:
            paras.append([ln.strip()])
            labels.append(f"제{_PARA_NO[pm.group(1)]}항")
        elif paras:
            paras[-1].append(ln.strip())
        else:  # text before ① (전문)
            paras.append([ln.strip()])
            labels.append("전문")

    if sum(1 for lb in labels if lb != "전문") < 2:
        return [("", a.text)]
    return [(lb, "\n".join(p)) for lb, p in zip(labels, paras)]


HO_RE = re.compile(r"^(\d+)\.\s")
MAX_CHUNK_CHARS = 1200   # passages longer than this are split again at top-level 호 ("1. ", "2. ", ...)

# 너무 긴 항은 호로 한 번 더 자름
def _split_long(label: str, text: str) -> List[Tuple[str, str]]:
    """Split one very long passage at its top-level 호 so the LLM can receive just the relevant 호."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [(label, text)]
    head: List[str] = []
    parts: List[Tuple[str, List[str]]] = []
    for ln in text.splitlines():
        hm = HO_RE.match(ln.strip())
        if hm:
            parts.append((f"{label} {hm.group(1)}호".strip(), [ln.strip()]))
        elif parts:
            parts[-1][1].append(ln.strip())
        else:
            head.append(ln.strip())
    if len(parts) < 2:
        return [(label, text)]
    out = [(label, "\n".join(head))] if head else []
    return out + [(lb, "\n".join(ls)) for lb, ls in parts]


def split_article(a: Article) -> List[Tuple[str, str]]:
    """Return [(label, text)] for one article: 항 first, very long 항 further split by 호."""
    out: List[Tuple[str, str]] = []
    for label, text in _split_paragraphs(a):
        out += _split_long(label, text)
    return out


def build_chunks(articles: List[Article]) -> List[Chunk]:
    chunks: List[Chunk] = []
    for i, a in enumerate(articles):
        parts = split_article(a)
        whole = len(parts) == 1 and parts[0][0] == ""
        for order, (label, text) in enumerate(parts):
            chunks.append(Chunk(i, order, label, text, whole, len(parts)))
    return chunks


def chunk_id(articles: List[Article], c: Chunk) -> str:
    return f"{articles[c.article_idx].id}#{c.order}"
