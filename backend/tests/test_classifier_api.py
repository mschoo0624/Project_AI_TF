from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile


@pytest.mark.parametrize(
    ("doc_text", "expected_input"),
    [
        ("사유 구분\n시험응시\n사유 내용\n자격시험 응시\n해당 기간\n2026년 9월 28일", "자격시험 응시"),
        ("진단서\n(주 질병·부상)\n급성 인두염\n진료일자", "급성 인두염"),
        ("알 수 없는 서류\n사유 내용 확인 불가", None),
    ],
)
def test_upload_classifies_only_supported_reason_text(monkeypatch, tmp_path, doc_text, expected_input):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "classifier_agent"))
    import API

    monkeypatch.setattr(API.submissions, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(API.extraction, "extract_text_from_pdf", lambda path: doc_text)
    monkeypatch.setattr(API.extraction, "extract_pdf", lambda text, source_file: {})
    monkeypatch.setattr(API.submissions, "create", lambda **kwargs: kwargs)
    predicted_inputs = []

    def predict(text):
        predicted_inputs.append(text)
        return "시험응시"

    monkeypatch.setattr(API.reason_classifier, "predict", predict)

    result = API.upload_submission(UploadFile(filename="test.pdf", file=BytesIO(b"%PDF-1.4")), None)

    assert predicted_inputs == ([expected_input] if expected_input else [])
    assert result["reason_category"] == ("시험응시" if expected_input else None)