import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "classifier_agent_old"))
from ML import extraction


def test_extraction_confidence_uses_text_evidence_not_model_claim(monkeypatch, tmp_path) -> None:
	monkeypatch.setattr(extraction, "DOCUMENT_EXTRACTIONS_PATH", tmp_path / "extractions.jsonl")
	model_output = json.dumps({
		"name": "틀린 이름",
		"valid_until": "2026-09-19",
		"document_type": "진단서",
		"stamp_present": True,
		"confidence": 0.95,
	}, ensure_ascii=False)
	monkeypatch.setattr(extraction, "_chat", lambda messages: model_output)

	result = extraction.extract_pdf(
		"진단서\n성명: 홍길동\n치료기간: 2026년 9월 20일\n[인]",
		source_file="sample.pdf",
	)

	assert result["confidence"] == 0.5
	assert result["confidence"] != 0.95
	assert result["confidence_basis"] == "text_evidence_match_rate_uncalibrated"
	assert result["confidence_details"] == [
		"성명: 원문 근거 불일치",
		"유효기간: 원문 근거 불일치",
		"문서 종류: 원문에서 확인",
		"도장/서명: 원문 텍스트 표기 확인",
	]


def test_extraction_confidence_is_zero_when_pdf_has_no_text(monkeypatch, tmp_path) -> None:
	monkeypatch.setattr(extraction, "DOCUMENT_EXTRACTIONS_PATH", tmp_path / "extractions.jsonl")
	monkeypatch.setattr(extraction, "_chat", lambda messages: pytest.fail("model should not run for empty PDF text"))

	result = extraction.extract_pdf("")

	assert result["confidence"] == 0.0
	assert result["confidence_basis"] == "text_evidence_match_rate_uncalibrated"
	assert "OCR" in result["error"]