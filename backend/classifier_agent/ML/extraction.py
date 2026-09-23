import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pypdf import PdfReader
"""
Using the Ollama API from the huggingface, for extracting the PDF texts.
- pip install ollama --break-system-packages
- pip install pypdf

Using the KoBART, HuggingFace Transformers for text generation and processing.
- pip install transformers --break-system-packages

pip install transformers torch

irm https://ollama.com/install.ps1 | iex
ollama --version

ollama pull llama3.2
ollama run llama3.2

curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull qwen2.5:7b
"""
import ollama

from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
""" 
 The model takes your system prompt + document text, converts it
 into tokens, and trained network, running on your own hardware instead of a company's servers.
"""
# Local-only Ollama client. Never falls back to a cloud endpoint (e.g. ollama.com).
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "qwen2.5:1.5b")
MAX_EXTRACTION_RETRIES = 2
_client = ollama.Client(host=OLLAMA_HOST)

# Structure of the extracted data from the PDF using the Ollama.
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "valid_until": {"type": "string"},
        "document_type": {"type": "string"},
        "stamp_present": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["name", "valid_until", "document_type", "stamp_present", "confidence"],
}

VALID_UNTIL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ExtractionResult:
    """구조화된 추출 결과 + 검증. 스키마 위반 필드는 errors 에 쌓입니다."""

    name: str = ""
    valid_until: str = ""
    document_type: str = ""
    stamp_present: bool = False
    confidence: float = 0.0
    errors: list[str] = field(default_factory=list)
    raw_output: str = ""

    @classmethod
    def from_raw(cls, output: str) -> "ExtractionResult":
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return cls(errors=["JSON 디코딩 실패"], raw_output=output)

        result = cls(
            name=str(data.get("name", "")),
            valid_until=str(data.get("valid_until", "")),
            document_type=str(data.get("document_type", "")),
            stamp_present=bool(data.get("stamp_present", False)),
            confidence=float(data["confidence"]) if _is_number(data.get("confidence")) else 0.0,
            raw_output=output,
        )
        result.errors = result._validate(data)
        return result

    def _validate(self, data: dict) -> list[str]:
        errors = []
        for req in JSON_SCHEMA["required"]:
            if req not in data:
                errors.append(f"필드 누락: {req}")
        if self.valid_until and not VALID_UNTIL_RE.match(self.valid_until):
            errors.append(f"valid_until 형식 오류: {self.valid_until!r} (YYYY-MM-DD 필요)")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append(f"confidence 범위 오류: {self.confidence}")
        return errors

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "valid_until": self.valid_until,
            "document_type": self.document_type,
            "stamp_present": self.stamp_present,
            "confidence": self.confidence,
        }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """실제 .pdf 파일에서 텍스트를 추출. 스캔본이라 텍스트 레이어가 없으면 빈 문자열 반환."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {path}")

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


#Giving the system prompt. To extract the PDF file information accurately.
EXTRACTION_SYSTEM_PROMPT = """당신은 예비군 관련 서류(진단서, 재직증명서, 사유확인서 등)에서 정보를 추출하는 어시스턴트입니다.
주어진 문서 텍스트에서 다음 필드를 정확히 추출하여 JSON으로만 응답하세요:
- name: 서류에 명시된 이름 (환자의 성명 등)
- valid_until: 서류의 유효기간 종료일 (YYYY-MM-DD 형식). '치료기간', '유효기간', '해당 기간', '입원·퇴원 연월일', '비고' 항목에
  적힌 기간의 마지막(종료) 날짜를 사용하세요. '2026년 9월 20일' 같은 표기는 '2026-09-20'으로 변환합니다.
  확인 불가능하면 빈 문자열로 두세요.
- document_type: 서류 최상단 제목에 적힌 서류 종류 (예: 진단서, 재직증명서, 사유확인서, 재학증명서, 출입국사실증명서 등).
  '사유 구분'란에 적힌 값(질병, 천재지변, 시험응시 등)은 document_type이 아니라 사유 분류이므로 절대 여기에 넣지 마세요.
- stamp_present: 도장/직인/[인] 표시가 있는 것으로 보이면 true, 아니면 false
- confidence: 추출 결과에 대한 0~1 사이의 신뢰도 in float
다른 설명 없이 JSON_SCHEMA 형식으로 반환하세요."""

KOREAN_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
VALID_UNTIL_KEYWORDS = ("치료기간", "유효기간", "퇴원", "비고", "해당 기간")


def _fallback_valid_until(doc_text: str) -> str:
    """모델이 valid_until을 비워둘 때, 텍스트에서 기간의 마지막 날짜를 직접 찾아보는 보조 수단."""
    for line in doc_text.splitlines():
        if any(keyword in line for keyword in VALID_UNTIL_KEYWORDS):
            dates = KOREAN_DATE_RE.findall(line)
            if dates:
                year, month, day = dates[-1]
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return ""


# 문서 제목은 한 글자씩 띄어 쓰는 관행(예: '사 유 확 인 서')이 있어 공백 제거 후 비교.
KNOWN_DOCUMENT_TYPES = ("진단서", "재직증명서", "사유확인서", "재학증명서", "출입국사실증명서", "수험표", "재해증명서")


def _detect_document_type(doc_text: str) -> str:
    """작은 로컬 모델이 '사유 구분' 등과 혼동하는 경우가 많아, 제목 줄에서 직접 판별."""
    for line in doc_text.splitlines()[:5]:
        normalized = line.replace(" ", "").strip()
        if normalized in KNOWN_DOCUMENT_TYPES:
            return normalized
    return ""


DOCUMENT_EXTRACTIONS_PATH = Path(__file__).with_name("document_extractions.jsonl")


def record_document_extraction(doc_text: str, fields: dict, source_file: str | None = None) -> None:
    entry = {"source_file": source_file, "text": doc_text, "fields": fields}
    with DOCUMENT_EXTRACTIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- 위조/이상 서류 규칙 기반 탐지 (파일명 REAL/FAKE 태그는 테스트용일 뿐, 실제로는 쓸 수 없음) ---

ONSET_VS_DIAGNOSIS_RE = re.compile(
    r"발병\s*연월일\D*?(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"
    r".*?진단\s*연월일\D*?(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    re.DOTALL,
)


def _all_dates(doc_text: str) -> list[tuple[int, int, int]]:
    return [(int(y), int(m), int(d)) for y, m, d in KOREAN_DATE_RE.findall(doc_text)]


def _standalone_dates(doc_text: str) -> list[tuple[int, int, int]]:
    """서명/확인 날짜는 보통 한 줄에 단독으로 적힙니다 (예: '...확인합니다.\\n2026년 8월 10일\\n확인기관')."""
    dates = []
    for line in doc_text.splitlines():
        match = KOREAN_DATE_RE.fullmatch(line.strip())
        if match:
            y, m, d = match.groups()
            dates.append((int(y), int(m), int(d)))
    return dates


def detect_anomalies(doc_text: str) -> list[str]:
    """문서 내용만으로 위조 의심 신호를 규칙 기반으로 탐지 (파일명에 의존하지 않음)."""
    flags = []

    if "미기재" in doc_text:
        flags.append("문서번호 미기재")

    if "(인)" not in doc_text and "[인]" not in doc_text:
        flags.append("직인/서명 표시 없음")

    onset_diag = ONSET_VS_DIAGNOSIS_RE.search(doc_text)
    if onset_diag:
        onset = tuple(int(v) for v in onset_diag.groups()[:3])
        diagnosis = tuple(int(v) for v in onset_diag.groups()[3:])
        if onset > diagnosis:
            flags.append("발병일이 진단일보다 늦음")

    # 근접일(수개월 이내) 사전 신청은 정상이므로, 수년 단위로 대괴되는 연대기만 플래그.
    ANACHRONISM_THRESHOLD_DAYS = 300
    signing_dates = _standalone_dates(doc_text)
    other_dates = [d for d in _all_dates(doc_text) if d not in signing_dates]
    if signing_dates and other_dates:
        signing_date = signing_dates[-1]
        earliest_other = min(other_dates)
        if signing_date < earliest_other:
            gap_days = (date(*earliest_other) - date(*signing_date)).days
            if gap_days > ANACHRONISM_THRESHOLD_DAYS:
                flags.append(f"서명/확인일이 사유 발생일보다 {gap_days}일 이상 이름 (연대 불일치)")

    return flags


def _chat(messages: list[dict]) -> str:
    try:
        response = _client.chat(
            model=EXTRACTION_MODEL,
            messages=messages,
            format=JSON_SCHEMA,
            options={"temperature": 0.1},
        )
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            raise RuntimeError(
                f"모델 '{EXTRACTION_MODEL}'을 로컬에서 찾을 수 없습니다. "
                f"`ollama pull {EXTRACTION_MODEL}`을 먼저 실행하세요."
            ) from exc
        raise RuntimeError(f"Ollama 요청 실패: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(
            f"로컬 Ollama 서버({OLLAMA_HOST})에 연결할 수 없습니다. "
            f"`ollama serve`로 서버를 먼저 실행하세요."
        ) from exc
    return response["message"]["content"]


def extract_pdf(doc_text: str, source_file: str | None = None) -> dict:
    """문서 텍스트에서 필드를 추출. 스키마 검증 실패 시 모델에게 재요청합니다."""
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": doc_text},
    ]

    result = ExtractionResult(errors=["추출 미실행"])
    for attempt in range(MAX_EXTRACTION_RETRIES + 1):
        output = _chat(messages)
        result = ExtractionResult.from_raw(output)
        if result.is_valid:
            break
        print(f"[extract_pdf] 검증 실패 (시도 {attempt + 1}/{MAX_EXTRACTION_RETRIES + 1}): {result.errors}")
        messages.append({"role": "assistant", "content": output})
        messages.append({
            "role": "user",
            "content": f"다음 오류를 수정해서 JSON_SCHEMA 형식으로 다시 응답하세요: {result.errors}",
        })

    res = result.to_dict()
    if not res["valid_until"]:
        res["valid_until"] = _fallback_valid_until(doc_text)
    detected_type = _detect_document_type(doc_text)
    if detected_type:
        res["document_type"] = detected_type
    if not result.is_valid:
        res["_raw_error"] = result.raw_output
        res["_errors"] = result.errors
    res["anomaly_flags"] = detect_anomalies(doc_text)
    res["source_file"] = source_file
    record_document_extraction(doc_text, res, source_file)
    return res


def extract_pdf_file(pdf_path: str | Path) -> dict:
    """PDF 파일 경로를 받아 텍스트 추출 + 필드 추출을 한 번에 수행."""
    doc_text = extract_text_from_pdf(pdf_path)
    return extract_pdf(doc_text, source_file=Path(pdf_path).name)


# Summarize the text from the json fromat using the KoBART model.
SUMMARIZATION_MODEL = "gogamza/kobart-summarization"
_summarization_tokenizer = None
_summarization_model = None

def load_summarization_model():
    global _summarization_tokenizer, _summarization_model
    if _summarization_tokenizer is None or _summarization_model is None:
        # Load the tokenizer and model for summarization if they haven't been loaded yet.
        _summarization_tokenizer = PreTrainedTokenizerFast.from_pretrained(SUMMARIZATION_MODEL)
        _summarization_model = BartForConditionalGeneration.from_pretrained(SUMMARIZATION_MODEL)

    return _summarization_tokenizer, _summarization_model

def summarize_text(text: str, MAX_LEN: int) -> str:
    # Load the summarization model and tokenizer if they haven't been loaded yet.
    token, model = load_summarization_model()

    inputs = token(text, return_tensors="pt", max_length=512, truncation=True)
    # Generate the summary using the model.
    res_id = model.generate(
        inputs["input_ids"],
        max_length=MAX_LEN,
        num_beams = 4,
        early_stopping = True
    )

    for i, res in enumerate(res_id):
        summary = token.decode(res, skip_special_tokens=True)
        print(f"Summary {i}: {summary}")

    return summary

"""--------------------------------------------------------------------------------------------"""
# Stage 2 (TF-IDF 사유 분류기) 학습 데이터가 여기 누적됩니다 — 100~200건 목표.
REASON_EXAMPLES_PATH = Path(__file__).with_name("reason_examples.jsonl")


def record_reason_example(text: str, summary: str, label: str | None = None, source_file: str | None = None) -> None:
    entry = {"source_file": source_file, "text": text, "summary": summary, "label": label}
    with REASON_EXAMPLES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def summarize_reason_pdf(pdf_path: str | Path, label: str | None = None) -> str:
    """개인사유서 PDF에서 텍스트를 추출해 요약하고, Stage 2 학습 데이터로 기록."""
    text = extract_text_from_pdf(pdf_path)
    summary = summarize_text(text, MAX_LEN=100)
    record_reason_example(text, summary, label, source_file=Path(pdf_path).name)
    return summary


# 샘플 파일명 규칙: {번호}_{REAL|FAKE}_{서류종류}.pdf — REAL/FAKE가 진위 판단의 ground truth.
BATCH_FILENAME_RE = re.compile(r"^\d+_(REAL|FAKE)_(.+)\.pdf$")
BATCH_RESULTS_PATH = Path(__file__).with_name("batch_test_results.jsonl")


def batch_test_pdfs(folder: str | Path, limit: int | None = None) -> list[dict]:
    """폴더 안 모든 PDF를 처리하고, 파일명에서 추출한 REAL/FAKE 진위 정보를 결과에 붙여줍니다."""
    files = sorted(Path(folder).glob("*.pdf"))
    if limit:
        files = files[:limit]

    results = []
    with BATCH_RESULTS_PATH.open("w", encoding="utf-8") as out:
        for i, path in enumerate(files, 1):
            match = BATCH_FILENAME_RE.match(path.name)
            authenticity, expected_type = match.groups() if match else (None, None)
            print(f"[{i}/{len(files)}] {path.name}")
            try:
                fields = extract_pdf_file(path)
                fields["authenticity"] = authenticity
                fields["expected_document_type"] = expected_type
                fields["type_match"] = bool(expected_type) and expected_type in fields.get("document_type", "")
            except Exception as exc:
                fields = {
                    "source_file": path.name,
                    "error": str(exc),
                    "authenticity": authenticity,
                    "expected_document_type": expected_type,
                }
            results.append(fields)
            out.write(json.dumps(fields, ensure_ascii=False) + "\n")
    return results


def summarize_batch(results: list[dict]) -> dict:
    total = len(results)
    errors = [r["source_file"] for r in results if "error" in r]
    with_expected = [r for r in results if r.get("expected_document_type")]
    type_matches = sum(1 for r in with_expected if r.get("type_match"))

    # authenticity 는 테스트용 정답(파일명)일 뿐, anomaly_flags 는 파일명을 전혀 보지 않고 문서
    # 내용만으로 판단합니다 — 아래는 그 규칙 기반 탐지의 정확도를 재는 평가용 집계입니다.
    labeled = [r for r in results if r.get("authenticity") in ("REAL", "FAKE")]
    flagged_and_fake = sum(1 for r in labeled if r.get("anomaly_flags") and r["authenticity"] == "FAKE")
    flagged_and_real = sum(1 for r in labeled if r.get("anomaly_flags") and r["authenticity"] == "REAL")
    total_fake = sum(1 for r in labeled if r["authenticity"] == "FAKE")
    total_real = sum(1 for r in labeled if r["authenticity"] == "REAL")

    return {
        "total": total,
        "errors": len(errors),
        "error_files": errors,
        "document_type_match": f"{type_matches}/{len(with_expected)}",
        "by_authenticity": dict(Counter(r.get("authenticity") for r in results)),
        "by_expected_type": dict(Counter(r.get("expected_document_type") for r in results)),
        "anomaly_detection_eval": {
            "recall_fake_flagged": f"{flagged_and_fake}/{total_fake}",
            "false_positive_real_flagged": f"{flagged_and_real}/{total_real}",
        },
    }


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="예비군 서류 추출/요약 (Stage 1)")
    parser.add_argument("--pdf", help="이 PDF 파일에서 필드를 추출 (진단서, 재직증명서 등)")
    parser.add_argument("--reason-pdf", help="이 개인사유서 PDF 파일을 요약")
    parser.add_argument("--label", help="--reason-pdf 사용 시 사유 분류 라벨 (선택)")
    parser.add_argument("--pdf-dir", help="이 폴더 안 모든 PDF를 일괄 처리해 배치 테스트")
    parser.add_argument("--limit", type=int, help="--pdf-dir 사용 시 처리할 파일 수 제한")
    parser.add_argument("--host", default=OLLAMA_HOST, help="로컬 Ollama 서버 주소")
    parser.add_argument("--model", default=EXTRACTION_MODEL, help="추출에 사용할 Ollama 모델")
    return parser.parse_args()


# TESTING PART.
if __name__ == "__main__":
    args = _parse_args()
    OLLAMA_HOST = args.host
    EXTRACTION_MODEL = args.model
    _client = ollama.Client(host=OLLAMA_HOST)
    if args.pdf:
        fields = extract_pdf_file(args.pdf)
        print(json.dumps(fields, ensure_ascii=False, indent=2))
    elif args.reason_pdf:
        summary = summarize_reason_pdf(args.reason_pdf, args.label)
        print(f"[{Path(args.reason_pdf).name}] {summary}")
    elif args.pdf_dir:
        results = batch_test_pdfs(args.pdf_dir, limit=args.limit)
        print(json.dumps(summarize_batch(results), ensure_ascii=False, indent=2))
        print(f"\n전체 결과: {BATCH_RESULTS_PATH}")
    else:
        print("--pdf <문서.pdf>, --reason-pdf <개인사유서.pdf>, 또는 --pdf-dir <폴더> 를 지정하세요.")