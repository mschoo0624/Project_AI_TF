"""Fast tests (no ML models needed):  python -m pytest"""
from pathlib import Path

import pytest

from legalrag.parser import parse_law_file, parse_law_text
from legalrag.references import extract_references, find_article_mentions
from legalrag.store import clean_text
from legalrag.tokenizer import tokenize

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

SAMPLE = """예비군법
[시행 2026. 8. 28.] [법률 제21388호, 2026. 2. 27., 일부개정]

제1조(목적)
제2조(임무)

예비군법
[시행 2026. 8. 28.] [법률 제21388호, 2026. 2. 27., 일부개정]
국방부(예비전력기획과) 02-748-5211

제1장 총칙
제1조(목적) 이 법은 예비군에 관한 사항을 정함을 목적으로 한다. <개정 2016. 5. 29.>
[전문개정 2010. 1. 25.]
제3조의2(편성) ① 제1조에 따른 예비군은 편성한다.
1. 첫째 호
제16조 삭제 <2010. 1. 25.>

부칙 <제21388호,2026. 2. 27.>
제1조(시행일) 이 법은 공포한 날부터 시행한다.
제2조(다른 법률의 개정) 병역법 일부를 다음과 같이 개정한다.
제49조제1항 중 "A"를 "B"로 한다.
"""


def test_parse_sample():
    arts = parse_law_text(SAMPLE, "sample")
    assert [a.article_no for a in arts] == ["제1조", "제3조의2", "제16조", "제1조", "제2조"]
    a1, a3, a16, b1, b2 = arts
    assert a1.law_name == "예비군법" and a1.law_type == "법률" and a1.promulgation_no == "제21388호"
    assert a1.effective_date == "2026-08-28" and a1.chapter == "제1장 총칙"
    assert a3.article_title == "편성" and "1. 첫째 호" in a3.text
    assert a3.refs == [{"law": "예비군법", "article": "제1조"}]
    assert a16.is_deleted
    assert b1.is_addendum and b1.id == "예비군법@21388::부칙::제1조"
    assert "제49조제1항" in b2.text  # amendment line stays inside 부칙 제2조


def test_references():
    refs = extract_references(
        "「예비군법」(이하 “법”이라 한다) 제3조의2제1항, 영 제5조제6항 및 「병역법」 제21조 및 제25조, 같은 법 시행령 제32조",
        self_law="예비군법 시행규칙",
    )
    assert refs == [
        {"law": "예비군법", "article": "제3조의2"},
        {"law": "예비군법 시행령", "article": "제5조"},
        {"law": "병역법", "article": "제21조"},
        {"law": "병역법", "article": "제25조"},
        {"law": "병역법 시행령", "article": "제32조"},
    ]


def test_article_mentions():
    laws = ["예비군법", "예비군법 시행령", "예비군법 시행규칙"]
    assert find_article_mentions("예비군법 시행령 제14조 알려줘", laws) == [{"law": "예비군법 시행령", "article": "제14조"}]
    assert find_article_mentions("「예비군법」 제6조의2", laws) == [{"law": "예비군법", "article": "제6조의2"}]
    assert find_article_mentions("제10조 내용", laws) == [{"law": None, "article": "제10조"}]


def test_tokenizer_and_clean():
    toks = tokenize("예비군대원은 훈련비를 받는다")
    assert "예비군대원" in toks and "훈련비" in toks and "훈련" in toks
    assert tokenize("제6조의2") == ["제6조의2"]
    assert clean_text("목적으로 한다. <개정 2016. 5. 29.>\n[전문개정 2010. 1. 25.]").strip() == "목적으로 한다."


@pytest.mark.skipif(not RAW.exists() or not any(RAW.glob("*.doc")), reason="no raw data")
def test_real_files_parse():
    for p in RAW.glob("*.doc"):
        arts = parse_law_file(p)
        main = [a for a in arts if not a.is_addendum]
        assert len(main) >= 15, p.name
        assert main[0].article_no == "제1조"
        assert len({a.id for a in arts}) == len(arts)
