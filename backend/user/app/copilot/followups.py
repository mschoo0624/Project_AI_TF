"""같은 대화 안의 후속 질문: "그럼 2소대는?", "그중 간부만", "해군만".

직전 질문이 인원 조회(search_members)였으면 그 조건을 이어받고, 새로 말한 조건만 바꿔서 다시 조회한다.
저장된 직전 답변이 아니라 저장된 **조건**을 다시 조회하므로, 그사이 데이터가 바뀌었어도 최신 결과가 나온다.
이해하지 못한 말이 남으면 추측하지 않고 일반 경로(규칙 → LLM)에 맡긴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.rules import SEARCH_ACTION_RE, Sentence, parse_filter, route
from user.app.copilot.schemas import ChatRequest
from user.app.copilot.tools import SearchMembersArgs
from user.app.models.copilot import CopilotConversation, CopilotMessage

# 앞 질문을 이어 간다는 말. "그중 간부만", "거기서 미편성만".
FOLLOWUP_RE = re.compile(
	r"^\s*(?:그럼|그러면|그렇다면|그\s*중에서|그\s*중|거기서|여기서|이번엔|이번에는|다시|그리고|아니면|근데)\s*[,，]?\s*"
)
# 직전 결과를 가리키는 말: 앞 조회가 없으면 의미가 없으므로 되묻는다.
NARROWING_RE = re.compile(r"^\s*(?:그\s*중|거기서|여기서)")
SHORT_FOLLOWUP = 15  # 이어 간다는 말 없이도, 이 글자 수 이하의 조건만 있는 말은 후속 질문으로 본다. 예: "해군만"


@dataclass(frozen=True)
class FollowUp:
	routed: tuple[str, BaseModel] | None = None   # 이어받아 만든 (도구, 인자)
	ask_back: str | None = None                   # 이어받을 앞 질문이 없을 때 되묻는 말


def _previous_search(db: Session, payload: ChatRequest) -> SearchMembersArgs | None:
	"""같은 사용자의 이 대화에서 **바로 앞 질문**이 인원 조회였으면 그 조건."""
	if not payload.conversation_id:
		return None
	conversation = db.get(CopilotConversation, payload.conversation_id)
	if conversation is None or conversation.owner != payload.client_id:
		return None
	last = db.scalars(select(CopilotMessage).where(CopilotMessage.conversation_id == conversation.id)
		.order_by(CopilotMessage.id.desc()).limit(1)).first()
	if last is None or last.tool != "search_members" or last.outcome != "answered" or not last.args_json:
		return None
	try:
		return SearchMembersArgs.model_validate_json(last.args_json)
	except ValidationError:
		return None


def merge(previous: SearchMembersArgs, new: SearchMembersArgs) -> SearchMembersArgs:
	"""앞 조건에 새 조건을 덮어쓴다. 서로 겹치는 조건(계급↔구분, 소대↔분대)은 새 것만 남긴다."""
	data = previous.conditions().model_dump(exclude_defaults=True)
	changed = new.conditions().model_dump(exclude_defaults=True)
	if "rank" in changed:
		data.pop("category", None)
	if "category" in changed:
		data.pop("rank", None)
	if "platoon" in changed and "squad" not in changed:
		data.pop("squad", None)  # 분대 번호는 소대 안에서만 뜻이 있다.
	if "assigned" in changed or "not_assignable" in changed:
		data.pop("assigned", None)
	data.update(changed)
	return SearchMembersArgs(**data)


def resolve(db: Session, payload: ChatRequest) -> FollowUp | None:
	"""후속 질문이면 이어받은 조회를, 아니면 None(일반 경로)을 돌려준다."""
	text = payload.message.strip()
	marker = FOLLOWUP_RE.match(text)
	body = text[marker.end():] if marker else text
	if not body:
		return None
	if marker:
		other = route(body)
		if isinstance(other, tuple) and other[0] != "search_members":
			return FollowUp(routed=other)  # "그럼 오늘 현황 보여줘": 조회가 아닌 새 요청이다.
	elif len(body) > SHORT_FOLLOWUP or isinstance(route(body), tuple):
		return None  # 그 자체로 완성된 질문은 일반 경로가 처리한다.

	sentence = Sentence(body)
	new = parse_filter(sentence)
	sentence.take(SEARCH_ACTION_RE)
	conditions = SearchMembersArgs(**new.conditions().model_dump())
	if sentence.leftover() or conditions.name or conditions.is_empty():
		return None  # 이해하지 못한 말이 남았으면 추측하지 않는다.

	previous = _previous_search(db, payload)
	if previous is None:
		# "그중 간부만"인데 이어받을 앞 조회가 없다. 전체에서 찾거나 '거기서'를 이름으로 읽지 않고 되묻는다.
		# "그럼 2소대 해군 병사 보여줘"처럼 조건이 다 들어 있는 말은 일반 경로가 처리한다.
		return FollowUp(ask_back=_ASK_BACK) if marker and NARROWING_RE.match(text) else None
	return FollowUp(routed=("search_members", merge(previous, conditions)))


_ASK_BACK = "어떤 조건에서 이어서 찾을지 모르겠어요. 먼저 명단을 조회하거나 조건을 함께 말씀해 주세요. 예: \"2소대 해군 병사 보여줘\""
