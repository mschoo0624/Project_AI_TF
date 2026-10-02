"""
Korean tokenizer for BM25 (keyword search).

Korean attaches particles to words ("예비군대원은", "예비군대원이", "예비군대원에게"), so exact
word matching fails. Instead of a morphological analyzer (extra dependency), we index:
  * the whole word (after stripping common particles/endings), and
  * character bigrams of Hangul words ("예비", "비군", "군대", ...)
Bigrams make "훈련비" match "훈련비를" and "동원훈련" match "동원 훈련".
"""
from __future__ import annotations

import re
from typing import List

_WORD_RE = re.compile(r"제\d+조(?:의\d+)?|[가-힣]+|[A-Za-z]+|\d+")
_PARTICLES = (
    "으로부터", "에게서", "으로서", "으로써", "에서는", "이라고", "에게는",
    "으로", "에게", "에서", "까지", "부터", "보다", "처럼", "마다", "이나", "이며", "하는", "하여", "한다",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만",
) # common particles are useless cuz they contain no meanings
_STOPWORDS = {"및", "또는", "그", "이", "그밖에", "등", "경우", "따라", "따른", "있다", "한다", "없다", "것", "수"} # useless cuz it appears too often


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for w in _WORD_RE.findall(text or ""):
        if w.startswith("제") and "조" in w and any(c.isdigit() for c in w):
            tokens.append(w)                    # keep article numbers intact: 제6조의2
            continue
        if not ("가" <= w[0] <= "힣"):
            tokens.append(w.lower())
            continue
        stem = _strip_particle(w)
        if stem in _STOPWORDS:
            continue
        tokens.append(stem)
        if len(stem) >= 2:
            tokens.extend(stem[i:i + 2] for i in range(len(stem) - 1))
    return tokens
