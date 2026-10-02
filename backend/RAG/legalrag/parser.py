"""
Korean statute text -> one record per article (조문).

Input is the plain text of a law.go.kr export, which looks like:

    예비군법                                         <- law name
    [시행 2026. 12. 10.] [법률 제21770호, 2026. 6. 9., 일부개정]
    제1조(목적)                                       <- table of contents (skipped)
    ...
    예비군법                                         <- body starts after the 2nd header
    [시행 2026. 12. 10.] [법률 제21770호, ...]
    제1장 총칙                                        <- chapter (장), optional 절
    제1조(목적) 이 법은 ... <개정 2016. 5. 29.>        <- article starts
    ① ... / 1. ...                                   <- continuation lines (항/호)
    [전문개정 2010. 1. 25.]
    제16조 삭제 <2010. 1. 25.>                        <- deleted article
    부칙 <제21770호,2026. 6. 9.>                      <- addenda (own 제1조, 제2조 ...)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from legalrag.references import extract_references

HEADER_RE = re.compile(
    r"^\[시행\s*(?P<eff>\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)\]\s*"
    r"\[(?P<type>[^\s\]]+)\s+(?P<no>제\d+호),\s*(?P<prom>\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.),?\s*(?P<kind>[^\]]*)\]"
)
CHAPTER_RE = re.compile(r"^제(?P<num>\d+)장(?:의(?P<sub>\d+))?\s*(?P<title>.*)$")
SECTION_RE = re.compile(r"^제(?P<num>\d+)절(?:의(?P<sub>\d+))?\s*(?P<title>.*)$")
# 제3조의2(예비군의 편성 및 해체 등) 본문...   /   제16조 삭제 <2010. 1. 25.>
ARTICLE_RE = re.compile(
    r"^제(?P<num>\d+)조(?:의(?P<sub>\d+))?"
    r"(?:\((?P<title>[^()]*(?:\([^()]*\)[^()]*)*)\))?"
    r"(?:\s+(?P<body>.*)|$)"
)
ADDENDUM_RE = re.compile(r"^부\s*칙\s*(?P<info><[^>]*>)?")
DELETED_RE = re.compile(r"^삭제\s*(<[^>]*>)?\s*$")


def _date(s: str) -> str:
    """'2026. 12. 10.' -> '2026-12-10'"""
    y, m, d = [int(x) for x in re.findall(r"\d+", s)[:3]]
    return f"{y:04d}-{m:02d}-{d:02d}"


@dataclass
class Article:
    id: str
    law_name: str
    law_type: str               # 법률 / 대통령령 / 국방부령
    promulgation_no: str        # 제21770호
    promulgation_date: str      # 2026-06-09
    effective_date: str         # 2026-12-10 (시행일)
    chapter: str                # 제1장 총칙 (부칙이면 "부칙 <...>")
    section: str                # 제1절 ...
    article_no: str             # 제3조의2 / 부칙
    article_title: str          # 예비군의 편성 및 해체 등
    is_addendum: bool           # 부칙 조문 여부
    is_deleted: bool            # "삭제"된 조문
    text: str                   # full article text (with 항/호 lines)
    source_file: str
    refs: List[Dict[str, str]] = field(default_factory=list)  # [{"law": ..., "article": "제6조"}]

    @property
    def display_name(self) -> str:
        prefix = "부칙 " if self.is_addendum and self.article_no != "부칙" else ""
        title = f"({self.article_title})" if self.article_title else ""
        return f"{self.law_name} {prefix}{self.article_no}{title}"

    def to_dict(self) -> Dict:
        return asdict(self)


def parse_law_text(text: str, source_file: str = "") -> List[Article]:
    lines = [ln.strip() for ln in text.splitlines()]

    # ---- header: law name + [시행 ...] [법률 제...호, ...] ----
    header_idx = [i for i, ln in enumerate(lines) if HEADER_RE.match(ln)]
    if not header_idx:
        raise ValueError(f"law header '[시행 ...]' not found in {source_file}")
    m = HEADER_RE.match(lines[header_idx[0]])
    law_name = next(ln for ln in lines[: header_idx[0]] if ln)  # first non-empty line
    meta = dict(
        law_name=law_name,
        law_type=m.group("type"),
        promulgation_no=m.group("no"),
        promulgation_date=_date(m.group("prom")),
        effective_date=_date(m.group("eff")),
        source_file=source_file,
    )
    version = m.group("no").strip("제호").lstrip("0")

    # ---- body starts after the LAST header (the first one is followed by a table of contents) ----
    body = lines[header_idx[-1] + 1:]

    articles: List[Article] = []
    chapter = section = ""
    in_addendum = False
    addendum_label = ""
    cur: Optional[dict] = None
    last_key = (0, 0)

    def finish() -> None:
        nonlocal cur
        if cur is None:
            return
        body_text = "\n".join(cur["lines"]).strip()
        if body_text:
            first_body = cur.get("first_body", "")
            art_prefix = "부칙::" if cur["is_addendum"] else ""
            articles.append(
                Article(
                    id=f"{law_name}@{version}::{art_prefix}{cur['article_no']}",
                    chapter=cur["chapter"],
                    section=cur["section"],
                    article_no=cur["article_no"],
                    article_title=cur["title"],
                    is_addendum=cur["is_addendum"],
                    is_deleted=bool(DELETED_RE.match(first_body)) and len(cur["lines"]) == 1,
                    text=body_text,
                    **meta,
                )
            )
        cur = None

    for ln in body:
        if not ln:
            continue

        am = ADDENDUM_RE.match(ln)
        if am:
            finish()
            in_addendum = True
            addendum_label = f"부칙 {am.group('info') or ''}".strip()
            chapter, section = addendum_label, ""
            last_key = (0, 0)
            # addendum without numbered articles -> collect its lines as one record
            cur = dict(article_no="부칙", title="", chapter=chapter, section="",
                       is_addendum=True, lines=[], first_body="")
            continue

        if not in_addendum:
            cm = CHAPTER_RE.match(ln)
            if cm:
                finish()
                chapter, section = ln, ""
                continue
            sm = SECTION_RE.match(ln)
            if sm:
                finish()
                section = ln
                continue

        art = ARTICLE_RE.match(ln)
        if art:
            key = (int(art.group("num")), int(art.group("sub") or 0))
            # article numbers only increase; this filters lines like "제49조 ..." inside 부칙 amendments
            if key > last_key:
                if cur is not None and cur["article_no"] == "부칙" and not cur["lines"]:
                    cur = None  # 부칙 header followed by numbered articles
                finish()
                last_key = key
                no = f"제{key[0]}조" + (f"의{key[1]}" if key[1] else "")
                cur = dict(
                    article_no=no,
                    title=(art.group("title") or "").strip(),
                    chapter=chapter,
                    section=section,
                    is_addendum=in_addendum,
                    lines=[ln],
                    first_body=(art.group("body") or "").strip(),
                )
                continue

        if cur is not None:
            cur["lines"].append(ln)

    finish()

    for a in articles:
        if not a.is_addendum:  # 부칙 often amends *other* laws; its references are unreliable
            a.refs = extract_references(a.text, self_law=a.law_name, self_article=a.article_no)
    return articles


def parse_law_file(path: str | Path) -> List[Article]:
    from legalrag.rtf import read_rtf

    path = Path(path)
    if path.suffix.lower() in (".doc", ".rtf"):
        text = read_rtf(path)
    else:
        text = path.read_text(encoding="utf-8")
    return parse_law_text(text, source_file=path.name)
