"""프론트엔드용 데이터 export.

    python export_frontend.py   →  frontend/public/data.json

기존 백엔드 코드(models.py / rules.py / assess.py / dataset.py)는
**전혀 건드리지 않습니다.** 이미 있는 assess() 결과를 JSON으로 떠서
파일로 저장할 뿐입니다.

실제 서버가 준비되면 이 파일이 하던 일을 API 엔드포인트가 대신하면
됩니다 — 프론트엔드의 fetch 대상만 `/data.json` 에서 실제 API 경로로
바꾸면 되고, 화면 코드는 그대로 씁니다. 아래에 그 대응표를 적어둡니다.

    화면이 필요로 하는 것          →  이 스크립트가 만드는 필드
    명부 (전체 236명 + 판정 결과)  →  data["people"]
    검토함 (대기 서류 + 미리보기)  →  data["queue"]
    반려/확인요청 버튼 목록        →  data["reject_reasons"], data["verify_reasons"]
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from assess import assess
from dataset import AS_OF, TRAINING, build_all
from models import DocStatus, DocType, REJECT_GUIDE, RejectReason, VerifyReason, accept

OUT = Path("frontend/public/data.json")


def doc_json(d, owner: str) -> dict:
    # 일부 실제 문서는 생성된 더미 PDF 대신 별도 원본 파일을 사용합니다.
    # 재학증명서는 실제 발급본을 그대로 열어야 하므로 경로를 강제 교체합니다.
    if d.doc_type == DocType.ENROLLMENT:
        file_path = "/재학증명서.pdf"
    else:
        # 파일은 dataset.py 의 "pdfs/employment.pdf" 처럼 상대경로로
        # 들어오므로, 여기서만 Vite public 서빙 경로로 변환합니다.
        file_path = f"/{d.file_path}" if d.file_path else None
    return {
        "type": d.doc_type.value,
        "issued": d.issued_date.isoformat(),
        "expiry": d.expiry().isoformat(),
        "status": d.status.value,
        "owner": owner,
        "file_path": file_path,
        "verify_number": d.verify_number or None,
        "reject_reason": d.reject_reason.value if d.reject_reason else None,
        "verify_reason": d.verify_reason.value if d.verify_reason else None,
        "reviewer": d.reviewer,
        "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None,
    }


def all_docs(p):
    """(고유id, Document, 소속표시) 전부. 본인 제출 + 연기신청 첨부."""
    for i, d in enumerate(p.documents):
        yield f"{p.person_id}#d{i}", d, "본인 제출"
    for j, req in enumerate(p.postponements):
        for i, d in enumerate(req.documents):
            yield f"{p.person_id}#p{j}-{i}", d, f"연기신청 · {req.reason.value}"


def person_json(p) -> dict:
    a = assess(p, AS_OF, TRAINING)
    docs = [{"id": doc_id, **doc_json(d, owner)} for doc_id, d, owner in all_docs(p)]
    return {
        "person_id": p.person_id,
        "name": p.name,
        "occupation": p.occupation,
        "branch": p.branch.value,
        "discharge_year": p.discharge_year,
        "mobilization_designated": p.mobilization_designated,
        "resource_year": a.resource_year,
        "classification": a.label,
        "exemption_type": a.exemption_type.value if a.exemption_type else None,
        "rule_code": a.exemption_rule,
        "mobilization": a.mobilization.value,
        "training": a.training.value,
        "hours": a.hours,
        "makeup_hours": a.makeup_hours,
        "carryover": a.carryover,
        "total_hours": a.total_hours,
        "reasons": a.reasons,
        "alerts": a.alerts,
        "pending_count": sum(1 for _, d, _ in all_docs(p) if d.status == DocStatus.PENDING),
        "documents": docs,
    }


def queue_rows(people) -> list[dict]:
    """검토 대기 서류. 승인 시 분류가 어떻게 바뀌는지 미리 계산합니다.

    화면에는 판정 '후에만' 노출하십시오 — 미리 보이면 '승인해도 안
    바뀌는' 서류를 덜 꼼꼼히 보게 됩니다.
    """
    rows = []
    for p in people:
        current = assess(p, AS_OF, TRAINING).label
        for doc_id, d, owner in all_docs(p):
            if d.status != DocStatus.PENDING:
                continue
            shadow = copy.deepcopy(p)
            for sid, sd, _ in all_docs(shadow):
                if sid == doc_id:
                    accept(sd, "PREVIEW")
                    break
            after = assess(shadow, AS_OF, TRAINING).label
            rows.append({
                "id": doc_id,
                "person_id": p.person_id,
                "person_name": p.name,
                "occupation": p.occupation,
                **doc_json(d, owner),
                "waiting_days": (AS_OF - d.issued_date).days,
                "current_classification": current,
                "if_accepted_classification": after,
            })
    rows.sort(key=lambda r: r["issued"])  # 제출 오래된 순 — 우선순위 매기지 않음
    return rows


def main() -> None:
    people, _ = build_all(200)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "as_of": AS_OF.isoformat(),
        "training_date": TRAINING.isoformat(),
        "reject_reasons": [
            {"code": r.name, "label": r.value,
             "can_resubmit": REJECT_GUIDE[r][0], "message": REJECT_GUIDE[r][1]}
            for r in RejectReason
        ],
        "verify_reasons": [{"code": r.name, "label": r.value} for r in VerifyReason],
        "people": [person_json(p) for p in people],
        "queue": queue_rows(people),
    }

    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    print(f"  인원 {len(data['people'])}명 / 검토대기 {len(data['queue'])}건")


if __name__ == "__main__":
    main()
