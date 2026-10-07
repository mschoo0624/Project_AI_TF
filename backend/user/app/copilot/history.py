"""
save_turn()이 현재 시간 생성 -> _conversation() 호출 및 질문, 답변 내용, 답변 경로,도구, 처리 결과 등을 CopilotMessage에 저장
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from user.app.copilot.schemas import (
	ChatRequest, ChatResponse, ConversationDetail, ConversationMessage, ConversationSummary,
)
from user.app.models.copilot import CopilotConversation, CopilotMessage

TITLE_LENGTH = 40
KEEP_FOR = timedelta(days=90)


def _now() -> datetime:
	return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc(moment: datetime | None) -> datetime | None:
	"""DB에는 UTC를 시간대 없이 저장한다. 화면이 오늘/어제를 나누도록 UTC라고 밝혀서 보낸다."""
	return moment.replace(tzinfo=timezone.utc) if moment is not None else None


def title_from(question: str) -> str:
	text = " ".join(question.split())
	return text if len(text) <= TITLE_LENGTH else text[:TITLE_LENGTH].rstrip() + "…"


def _conversation(db: Session, payload: ChatRequest, now: datetime) -> CopilotConversation:
	"""이어서 묻는 대화를 찾는다. 다른 브라우저의 대화이거나 지워졌으면 새 대화를 시작한다."""
	if payload.conversation_id:
		found = db.get(CopilotConversation, payload.conversation_id)
		if found is not None and found.owner == payload.client_id:
			return found
	delete_old(db, now)
	conversation = CopilotConversation(
		id=uuid.uuid4().hex, owner=payload.client_id, title=title_from(payload.message),
		created_at=now, updated_at=now,
	)
	db.add(conversation)
	return conversation


def delete_old(db: Session, now: datetime) -> None:
	"""질문에는 이름·군번이 들어 있어 90일이 지난 대화는 지운다. 데이터 변경은 AuditLog에 그대로 남는다."""
	old = select(CopilotConversation.id).where(CopilotConversation.updated_at < now - KEEP_FOR)
	db.execute(delete(CopilotMessage).where(CopilotMessage.conversation_id.in_(old)))
	db.execute(delete(CopilotConversation).where(CopilotConversation.updated_at < now - KEEP_FOR))


def save_turn(db: Session, payload: ChatRequest, response: ChatResponse, *, outcome: str,
		args: BaseModel | None, used_context: bool, latency_ms: int) -> str:
	"""Save one question and its answer; return the conversation id."""
	now = _now()
	conversation = _conversation(db, payload, now)
	conversation.updated_at = now
	response.conversation_id = conversation.id
	db.add(CopilotMessage(
		conversation_id=conversation.id,
		trace_id=response.trace_id,
		created_at=now,
		question=payload.message,
		response_json=response.model_dump_json(),
		routed_by=response.routed_by,
		tool=response.tool,
		args_json=args.model_dump_json(exclude_defaults=True) if args is not None else None,
		unparsed_json=json.dumps(response.unparsed, ensure_ascii=False) if response.unparsed else None,
		outcome=outcome,
		used_context=used_context,
		latency_ms=latency_ms,
	))
	db.commit()
	return conversation.id


def _message(db: Session, trace_id: str | None) -> CopilotMessage | None:
	if not trace_id:
		return None
	return db.scalars(select(CopilotMessage).where(CopilotMessage.trace_id == trace_id)).first()


def already_applied(db: Session, trace_id: str | None) -> bool:
	message = _message(db, trace_id)
	return message is not None and message.applied_at is not None


def mark_applied(db: Session, trace_id: str | None, summary: str) -> None:
	message = _message(db, trace_id)
	if message is None:
		return
	message.applied_at = _now()
	message.applied_summary = summary
	db.commit()


def owned_message(db: Session, trace_id: str, owner: str) -> CopilotMessage | None:
	"""이 브라우저의 대화에 있는 질문만 되돌릴 수 있다."""
	message = _message(db, trace_id)
	if message is None:
		return None
	conversation = db.get(CopilotConversation, message.conversation_id)
	return message if conversation is not None and conversation.owner == owner else None


def mark_undone(db: Session, message: CopilotMessage, summary: str) -> datetime:
	message.undone_at = _now()
	message.undone_summary = summary
	db.commit()
	return _utc(message.undone_at)


def list_conversations(db: Session, owner: str, limit: int = 50) -> list[ConversationSummary]:
	changes = (
		select(CopilotMessage.conversation_id, func.count().label("changes"),
			func.count(CopilotMessage.undone_at).label("undone"))
		.where(CopilotMessage.applied_at.is_not(None))
		.group_by(CopilotMessage.conversation_id)
		.subquery()
	)
	rows = db.execute(
		select(CopilotConversation, func.coalesce(changes.c.changes, 0), func.coalesce(changes.c.undone, 0))
		.outerjoin(changes, changes.c.conversation_id == CopilotConversation.id)
		.where(CopilotConversation.owner == owner)
		.order_by(CopilotConversation.updated_at.desc())
		.limit(limit)
	).all()
	return [
		ConversationSummary(id=conversation.id, title=conversation.title,
			updated_at=_utc(conversation.updated_at), changes=count, undone=undone)
		for conversation, count, undone in rows
	]


def get_conversation(db: Session, conversation_id: str, owner: str) -> ConversationDetail | None:
	conversation = db.get(CopilotConversation, conversation_id)
	if conversation is None or conversation.owner != owner:
		return None
	messages = db.scalars(
		select(CopilotMessage).where(CopilotMessage.conversation_id == conversation_id)
		.order_by(CopilotMessage.created_at, CopilotMessage.id)
	).all()
	return ConversationDetail(id=conversation.id, title=conversation.title, messages=[
		ConversationMessage(
			question=message.question,
			response=ChatResponse.model_validate_json(message.response_json),
			created_at=_utc(message.created_at),
			applied_at=_utc(message.applied_at),
			applied_summary=message.applied_summary,
			undone_at=_utc(message.undone_at),
			undone_summary=message.undone_summary,
		)
		for message in messages
	])
