"""업로드된 PDF 제출 건 저장소.

관리자가 업로드된 서류의 AI 추출/분류 결과를 보고 승인/반려하는 흐름을
지원하기 위한 아주 단순한 JSONL 기반 저장소입니다. 실제 DB가 생기기
전까지만 쓰는 임시 구조입니다.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

SUBMISSIONS_PATH = Path(__file__).with_name("submissions.jsonl")
UPLOAD_DIR = Path(__file__).with_name("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

STATUSES = ("pending", "approved", "declined")


def _load_all() -> list[dict]:
    if not SUBMISSIONS_PATH.exists():
        return []
    with SUBMISSIONS_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _save_all(submissions: list[dict]) -> None:
    with SUBMISSIONS_PATH.open("w", encoding="utf-8") as f:
        for s in submissions:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def create(
    filename: str,
    saved_path: str,
    extraction_fields: dict,
    reason_category: str | None,
    military_number: str | None = None,
) -> dict:
    submission = {
        "id": uuid.uuid4().hex,
        "filename": filename,
        "saved_path": saved_path,
        "military_number": military_number,
        "extraction": extraction_fields,
        "reason_category": reason_category,
        "status": "pending",
        "note": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decided_at": None,
    }
    submissions = _load_all()
    submissions.append(submission)
    _save_all(submissions)
    return submission


def list_all() -> list[dict]:
    return list(reversed(_load_all()))


def get(submission_id: str) -> dict | None:
    for s in _load_all():
        if s["id"] == submission_id:
            return s
    return None


def decide(submission_id: str, decision: str, note: str | None = None) -> dict | None:
    if decision not in ("approved", "declined"):
        raise ValueError(f"decision 은 approved/declined 여야 합니다: {decision!r}")

    submissions = _load_all()
    updated = None
    for s in submissions:
        if s["id"] == submission_id:
            s["status"] = decision
            s["note"] = note
            s["decided_at"] = datetime.now(timezone.utc).isoformat()
            updated = s
            break
    if updated is not None:
        _save_all(submissions)
    return updated
