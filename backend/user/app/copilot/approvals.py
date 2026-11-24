"""Read-only Copilot tool: 결재 대기 중인 보류·연기 신청 목록과 서류 상태.

Nothing here writes to the DB. 서류 상태는 연결된 문서 AI 분석 제출(classifier_submission_id)의
검증 결과를 읽어 알려 줄 뿐이며, 승인·반려 판단은 하지 않는다.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot import laws
from user.app.copilot.common import ToolResult
from user.app.copilot.schemas import UiAction
from user.app.models.person import Person
from user.app.models.postpoment import Postponement

logger = logging.getLogger(__name__)

TYPE_NAMES = {"hold": "보류", "보류": "보류", "delay": "연기", "연기": "연기"}
VERIFICATION_NAMES = {
	"sufficient": "근거 충족", "insufficient": "근거 부족", "not_met": "요건 불충족", "review_required": "담당자 검토 필요",
}
NO_DOCUMENT, NOT_VERIFIED, UNREADABLE = "서류 없음", "검증 전", "문서 확인 불가"
# 담당자가 서류를 더 받아야 하는 상태
INCOMPLETE = {NO_DOCUMENT, "근거 부족", "요건 불충족"}
SHOWN = 10


class PendingPostponementsArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: Literal["보류", "연기"] | None = Field(default=None, description="신청 종류. 말하지 않으면 보류·연기 모두")
	incomplete_documents: bool = Field(
		default=False, description="true=서류가 없거나 근거가 부족·불충족인 신청만 (예: '서류가 빠진 신청')")


def _document_state(postponement: Postponement) -> tuple[str, list[str]]:
	"""(상태, 부족한 항목). 연결된 문서 AI 분석 제출이 없으면 서류가 없는 것으로 본다."""
	submission_id = postponement.classifier_submission_id
	if not submission_id:
		return (NOT_VERIFIED if postponement.source_file else NO_DOCUMENT), []
	try:
		from classifier_agent import submissions

		item = submissions.get(submission_id)
	except Exception:  # 제출 저장소를 못 읽어도 목록 자체는 보여 준다.
		logger.warning("제출 %s를 읽지 못했습니다", submission_id, exc_info=True)
		return UNREADABLE, []
	verification = item.get("verification")
	if not isinstance(verification, dict):
		return NOT_VERIFIED, []
	state = VERIFICATION_NAMES.get(str(verification.get("result")), NOT_VERIFIED)
	missing = [str(key) for key in (verification.get("missing_information") or [])]
	return state, missing


def pending_items(db: Session, args: PendingPostponementsArgs) -> tuple[list[tuple[Postponement, str, list[str]]], dict[str, Person]]:
	"""결재 대기 신청 [(신청, 서류 상태, 부족 항목)]과 신청자들. 목록 답변과 내보내기가 같이 쓴다."""
	rows = list(db.scalars(select(Postponement).where(Postponement.status == "pending").order_by(Postponement.id)).all())
	rows = [row for row in rows if args.kind is None or TYPE_NAMES.get(row.type, row.type) == args.kind]
	people = {person.military_number: person for person in db.scalars(
		select(Person).where(Person.military_number.in_({row.person_id for row in rows}))).all()} if rows else {}

	items = []
	for row in rows:
		state, missing = _document_state(row)
		if args.incomplete_documents and state not in INCOMPLETE:
			continue
		items.append((row, state, missing))
	return items, people


def list_pending_postponements(db: Session, args: PendingPostponementsArgs) -> ToolResult:
	items, people = pending_items(db, args)

	scope = f"{args.kind} " if args.kind else "보류·연기 "
	what = "서류가 미비한 " if args.incomplete_documents else ""
	if not items:
		return ToolResult(f"{what}결재 대기 {scope}신청이 없어요.")

	counts: dict[str, int] = {}
	for _, state, _ in items:
		counts[state] = counts.get(state, 0) + 1
	summary = " · ".join(f"{state} {count}건" for state, count in sorted(counts.items(), key=lambda pair: -pair[1]))
	lines = []
	for row, state, missing in items[:SHOWN]:
		person = people.get(row.person_id)
		who = f"{person.name}({row.person_id})" if person else row.person_id
		reason = (row.reason or "").strip()
		reason = reason if len(reason) <= 20 else reason[:20] + "…"
		detail = f" [부족: {', '.join(missing[:3])}]" if missing else ""
		lines.append(f"· {who} {TYPE_NAMES.get(row.type, row.type)} — {reason or '사유 없음'} · {state}{detail}")
	more = f"\n외 {len(items) - SHOWN}건은 인원 목록에 필터로 걸어 두었어요." if len(items) > SHOWN else ""
	message = f"{what}결재 대기 {scope}신청은 {len(items)}건이에요. ({summary})\n" + "\n".join(lines) + more
	# 판단 근거가 되는 법령을 같이 보여 준다(법령 챗봇의 검색 결과를 그대로 인용, 요약·판단 없음).
	kinds = {TYPE_NAMES.get(row.type, row.type) for row, _, _ in items}
	message += laws.reference_block(sorted(kinds))

	ids = [row.person_id for row, _, _ in items if row.person_id in people]
	actions = [UiAction(type="navigate", tab="roster", subtab="people"),
		UiAction(type="filter", tab="roster", ids=list(dict.fromkeys(ids)),
			# 이 라벨을 보고 "이 명단 엑셀로"가 사람 명단이 아닌 신청 목록을 내보낸다(router._export_target).
			label=f"{'서류 미비 ' if args.incomplete_documents else ''}결재 대기 {scope}신청".strip())] if ids else []
	return ToolResult(message, actions, conditions=[f"결재 대기", *( [args.kind] if args.kind else [] ),
		*(["서류 미비"] if args.incomplete_documents else [])])
