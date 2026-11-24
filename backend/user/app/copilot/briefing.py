"""Read-only: 채팅을 열면 먼저 보여 주는 "오늘 확인할 일".

숫자는 오늘 현황(insights.collect_status)과 같은 계산이다. 항목마다 눌러서 바로 물어볼 문장을 함께 준다.
0건인 항목은 보여 주지 않는다. DB를 바꾸지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot import memory
from user.app.copilot.approvals import INCOMPLETE, _document_state
from user.app.copilot.changes import changed_people
from user.app.copilot.insights import collect_status
from user.app.models.postpoment import Postponement


class BriefingItem(BaseModel):
	text: str
	prompt: str  # 누르면 채팅으로 보낼 문장


class Briefing(BaseModel):
	items: list[BriefingItem]  # 오늘 확인할 일 (DB 현황)
	unfinished: list[BriefingItem] = []  # 지난 대화에서 승인하지 않고 둔 제안
	frequent: list[BriefingItem] = []  # 자주 쓰는 요청


def build_briefing(db: Session, owner: str | None = None) -> Briefing:
	snap = collect_status(db)
	pending = list(db.scalars(select(Postponement).where(Postponement.status == "pending")).all())
	incomplete = sum(1 for row in pending if _document_state(row)[0] in INCOMPLETE)

	changed = len(changed_people(db, "오늘"))
	candidates = [
		(changed, f"오늘 수정된 인원 {changed}명", "오늘 수정한 인원 보여줘"),
		(snap.pending_postponements, f"보류·연기 결재 대기 {snap.pending_postponements}건", "결재 대기 목록 보여줘"),
		(incomplete, f"서류가 빠진 신청 {incomplete}건", "서류가 빠진 신청 보여줘"),
		(snap.pending_transfers, f"전입 확인 대기 {snap.pending_transfers}건", "방금 등록한 전입자 어디 편성하면 돼?"),
		(len(snap.unassigned), f"미편성 인원 {len(snap.unassigned)}명", "미편성 인원들 편성해줘"),
		(len(snap.short), f"교육 시간 미달 {len(snap.short)}명", "교육 미달자 보여줘"),
		(len(snap.prosecution), f"고발 검토 대상 {len(snap.prosecution)}명", "고발 대상자 보여줘"),
		(len(snap.issues), f"이상 데이터 {len(snap.issues)}종류", "이상 데이터 점검해줘"),
	]
	remembered = (memory.unfinished(db, owner), memory.frequent(db, owner)) if owner else ([], [])
	return Briefing(
		items=[BriefingItem(text=text, prompt=prompt) for count, text, prompt in candidates if count > 0],
		unfinished=[BriefingItem(text=text, prompt=prompt) for text, prompt in remembered[0]],
		frequent=[BriefingItem(text=question, prompt=question) for question in remembered[1]],
	)
