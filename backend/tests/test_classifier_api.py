from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_text_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = stream
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


def test_upload_extracts_text_from_real_pdf_attachment(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "classifier_agent"))
    import API

    monkeypatch.setattr(API.submissions, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(API.submissions, "create", lambda **kwargs: kwargs)
    extracted_text = []
    monkeypatch.setattr(
        API.extraction,
        "extract_pdf",
        lambda text, source_file: extracted_text.append((text, source_file)) or {},
    )

    result = API.upload_submission(
        UploadFile(
            filename="actual-attachment.pdf",
            file=BytesIO(make_text_pdf("Medical Certificate")),
        ),
        None,
    )

    assert extracted_text == [("Medical Certificate", "actual-attachment.pdf")]
    assert result["filename"] == "actual-attachment.pdf"