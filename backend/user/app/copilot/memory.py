"""Read-only: 지난 대화에서 기억해 두었다가 다음 업무에 도움이 되는 것.

같은 브라우저(owner)의 질문 기록(copilot_message)만 읽는다. 기억한 답변을 다시 보여 주는 게 아니라
**같은 질문을 다시 던지게** 해서 항상 지금 데이터로 답하게 한다(그사이 데이터가 바뀌었을 수 있다).
  · unfinished: 제안 카드를 받고 승인하지 않은 채 둔 요청
  · frequent:   최근 30일에 자주 한 질문
DB를 바꾸지 않는다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.schemas import ChatResponse
from user.app.models.copilot import CopilotConversation, CopilotMessage

KST = timezone(timedelta(hours=9))
UNFINISHED_WITHIN = timedelta(days=3)  # 이보다 오래된 제안은 데이터가 많이 바뀌었을 테니 보여 주지 않는다.
FREQUENT_WITHIN = timedelta(days=30)
FREQUENT_MIN = 2  # 이 횟수 이상 물어본 질문만
SHOWN_UNFINISHED, SHOWN_FREQUENT = 2, 3
# 다시 물어도 데이터를 바꾸지 않는 도구만 "자주 쓰는 요청"으로 추천한다. 내보내기는 파일만 새로 만든다.
REPEATABLE = {
	"summarize_status", "list_pending_postponements", "draft_status_report", "search_members", "check_data_issues",
	"show_recent_changes", "list_changed_people", "export_list", "explain_squad_shortage",
}


def _normal(question: str) -> str:
	return " ".join(question.split())


def _owned(db: Session, owner: str, since: datetime) -> list[CopilotMessage]:
	return list(db.scalars(
		select(CopilotMessage).join(CopilotConversation, CopilotConversation.id == CopilotMessage.conversation_id)
		.where(CopilotConversation.owner == owner, CopilotMessage.created_at >= since)
		.order_by(CopilotMessage.created_at, CopilotMessage.id)
	).all())


def _when(moment: datetime, now: datetime) -> str:
	local = moment.replace(tzinfo=timezone.utc).astimezone(KST)
	today = now.replace(tzinfo=timezone.utc).astimezone(KST).date()
	day = "오늘" if local.date() == today else "어제" if local.date() == today - timedelta(days=1) else local.strftime("%m/%d")
	return f"{day} {local:%H:%M}"


def unfinished(db: Session, owner: str, now: datetime | None = None) -> list[tuple[str, str]]:
	"""(안내 문장, 다시 물을 질문). 같은 질문은 가장 최근 것만 보고, 그 뒤에 승인했으면 빼 준다."""
	now = now or datetime.now(timezone.utc).replace(tzinfo=None)
	latest: dict[str, CopilotMessage] = {}
	for message in _owned(db, owner, now - UNFINISHED_WITHIN):
		if message.outcome == "answered":
			latest[_normal(message.question)] = message  # 시간순이라 뒤의 것이 덮어쓴다.
	items = []
	for question, message in sorted(latest.items(), key=lambda pair: pair[1].created_at, reverse=True):
		if message.applied_at is not None:
			continue
		try:
			if ChatResponse.model_validate_json(message.response_json).proposal is None:
				continue
		except ValueError:
			continue
		items.append((f"승인하지 않은 제안: {question} ({_when(message.created_at, now)})", question))
	return items[:SHOWN_UNFINISHED]


def frequent(db: Session, owner: str, now: datetime | None = None) -> list[str]:
	"""최근 30일에 FREQUENT_MIN번 이상 한 질문, 많이 한 순(같으면 최근 순)."""
	now = now or datetime.now(timezone.utc).replace(tzinfo=None)
	counts: dict[str, int] = defaultdict(int)
	last: dict[str, datetime] = {}
	for message in _owned(db, owner, now - FREQUENT_WITHIN):
		# 앞 대화에 기대는 말("저 인원들")은 혼자서는 뜻이 없고, 규칙이 못 알아들은 말은 추천할 이유가 없다.
		if message.outcome != "answered" or message.used_context or message.tool not in REPEATABLE:
			continue
		question = _normal(message.question)
		counts[question] += 1
		last[question] = message.created_at
	ranked = sorted((q for q, count in counts.items() if count >= FREQUENT_MIN), key=lambda q: (-counts[q], -last[q].timestamp()))
	return ranked[:SHOWN_FREQUENT]
