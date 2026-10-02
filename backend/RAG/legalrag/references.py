"""
Find article references (조문 인용) inside Korean statute text.

Examples (inside 예비군법 시행규칙):
    "법 제6조제1항에 따라"          -> 예비군법 제6조
    "영 제32조"                   -> 예비군법 시행령 제32조
    "「예비군법」 제14조의3"         -> 예비군법 제14조의3
    "같은 법 시행령 제32조"          -> 예비군법 시행령 제32조   (같은 법 = last quoted law)
    "제5조제2항"                   -> (this law) 제5조
    "「병역법」 제65조"             -> 병역법 제65조 (not in our corpus -> ignored when resolving)
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# Abbreviations used by the 예비군 subordinate statutes: "법" = 예비군법, "영" = 예비군법 시행령
ABBREVIATIONS = {
    "법": "예비군법",
    "영": "예비군법 시행령",
    "규칙": "예비군법 시행규칙",
}

REF_RE = re.compile(
    r"(?:"
    r"「(?P<quoted>[^」]+)」\s*"
    r"|(?P<same>같은\s*법(?:\s*시행령|\s*시행규칙)?)\s*"
    r"|(?<![가-힣])(?P<this>이\s*)?(?P<abbr>법|영|규칙)\s+"
    r")?"
    r"제(?P<num>\d+)조(?:의(?P<sub>\d+))?"
)
_QUOTED_THEN_PAREN_RE = re.compile(r"「([^」]+)」\s*\([^()]*\)\s*$")
# text allowed between two items of one list: "제1항제2호, 제5조" / "제6조의2 및 제6조의3"
_LIST_GAP_RE = re.compile(r"(?:제\d+(?:항|호|목)(?:의\d+)?|[\s,ㆍ·]|및|또는|부터|까지|와|과|본문|단서|전단|후단)*")


def article_no(num: str | int, sub: Optional[str | int] = None) -> str:
    return f"제{int(num)}조" + (f"의{int(sub)}" if sub and int(sub) else "")


def extract_references(text: str, self_law: str, self_article: str = "") -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    seen = set()
    prev_law: Optional[str] = None
    prev_end = 0

    for m in REF_RE.finditer(text):
        start = m.start()
        # "부칙 제3조" / "같은 조" etc. are not article references of a statute
        if text[max(0, start - 3):start].strip().endswith("부칙"):
            continue

        if m.group("quoted"):
            law = m.group("quoted").strip()
        elif m.group("same"):
            quoted_before = re.findall(r"「([^」]+)」", text[:start])
            base = quoted_before[-1].strip() if quoted_before else self_law
            same = re.sub(r"\s+", " ", m.group("same"))
            if "시행령" in same:
                law = f"{base} 시행령"
            elif "시행규칙" in same:
                law = f"{base} 시행규칙"
            else:
                law = base
        elif m.group("abbr"):
            law = self_law if m.group("this") else ABBREVIATIONS.get(m.group("abbr"), self_law)
            # inside 예비군법 itself "법" can only mean itself
            if law == ABBREVIATIONS["법"] and self_law == ABBREVIATIONS["법"]:
                law = self_law
        else:
            # bare "제N조" -> this law, unless
            #  a) it continues a list: "같은 법 제21조 및 제25조" (제25조 is also 같은 법)
            #  b) it follows a quoted law + parenthetical: 「예비군법」(이하 “법”이라 한다) 제14조의3
            pm = _QUOTED_THEN_PAREN_RE.search(text[max(0, start - 80):start])
            if prev_law is not None and _LIST_GAP_RE.fullmatch(text[prev_end:start]):
                law = prev_law
            elif pm:
                law = pm.group(1).strip()
            else:
                law = self_law
        prev_law, prev_end = law, m.end()

        art = article_no(m.group("num"), m.group("sub"))
        if law == self_law and art == self_article:
            continue
        key = (law, art)
        if key not in seen:
            seen.add(key)
            refs.append({"law": law, "article": art})
    return refs


def find_article_mentions(query: str, known_laws: List[str]) -> List[Dict[str, Optional[str]]]:
    """
    Detect explicit article mentions in a user question, e.g. "예비군법 시행령 제10조는?"
    Returns [{"law": "예비군법 시행령" | None, "article": "제10조"}]. law=None means "any law".
    """
    out = []
    # longest law names first so "예비군법 시행령" wins over "예비군법"
    laws = sorted(known_laws, key=len, reverse=True)
    for m in re.finditer(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?", query):
        before = query[: m.start()].rstrip().replace("「", "").replace("」", "")
        law = next((name for name in laws if before.endswith(name)), None)
        if law is None:
            # "시행령 제10조" / "시행규칙 제3조"
            for suffix, full in (("시행령", "예비군법 시행령"), ("시행규칙", "예비군법 시행규칙")):
                if before.endswith(suffix) and full in known_laws:
                    law = full
                    break
        out.append({"law": law, "article": article_no(m.group(1), m.group(2))})
    return out
