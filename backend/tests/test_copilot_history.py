"""Copilot 대화 기록: 질문·답 저장, 브라우저별 목록, 승인 표시, 질문 검토용 기록."""

import dataclasses
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.copilot import history, llm
from user.app.copilot.router import apply, chat, conversation, conversations, delete_conversation
from user.app.copilot.schemas import ApplyRequest, ChatContext, ChatRequest
from user.app.models.copilot import CopilotConversation, CopilotMessage
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad

ME = "browser-aaaa1111"
OTHER = "browser-bbbb2222"


def make_session() -> Session:
	engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	return Session(engine)


def seed(db: Session) -> None:
	"""1소대 1분대에 0년차 1명, 5년차 1명."""
	db.add(Squad(id=1, name="1분대"))
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		OrganizationNode(id=10, parent_id=1, kind="platoon", name="1소대"),
		OrganizationNode(id=11, parent_id=10, kind="squad", name="1분대", squad_id=1, planned_strength=11),
	])
	for number, year in (("0-1", 0), ("5-1", 5)):
		db.add(Person(military_number=number, name=number, branch="육군", rank="병장", service_year=year,
			position="소총수", mobilization_status="동원지정", status="active", squad_id=1))
	db.commit()


def ask(db: Session, message: str, client_id: str | None = ME, conversation_id: str | None = None, **extra):
	return chat(ChatRequest(message=message, client_id=client_id, conversation_id=conversation_id, **extra), db)


def logged(db: Session, trace_id: str) -> CopilotMessage:
	return db.scalars(select(CopilotMessage).where(CopilotMessage.trace_id == trace_id)).one()


def test_questions_continue_one_conversation_per_browser() -> None:
	db = make_session()
	seed(db)

	first = ask(db, "0년차 편성된 사람 보여줘")
	assert first.conversation_id
	second = ask(db, "오늘 현황", conversation_id=first.conversation_id)
	assert second.conversation_id == first.conversation_id
	ask(db, "최근 변경 기록", client_id=OTHER)

	mine = conversations(client_id=ME, db=db)
	assert [(item.title, item.changes) for item in mine] == [("0년차 편성된 사람 보여줘", 0)]
	assert mine[0].updated_at.tzinfo is not None  # 화면이 오늘/어제를 나눌 수 있게 UTC로 보낸다

	opened = conversation(first.conversation_id, client_id=ME, db=db)
	assert [message.question for message in opened.messages] == ["0년차 편성된 사람 보여줘", "오늘 현황"]
	assert opened.messages[0].response.message == first.message  # 다시 열어도 같은 답이 보인다


def test_other_browser_cannot_open_or_continue_my_conversation() -> None:
	db = make_session()
	seed(db)
	mine = ask(db, "오늘 현황")

	with pytest.raises(HTTPException) as error:
		conversation(mine.conversation_id, client_id=OTHER, db=db)
	assert error.value.status_code == 404
	# 남의 대화 ID로 물으면 그 대화에 끼어들지 않고 새 대화를 시작한다.
	theirs = ask(db, "최근 변경 기록", client_id=OTHER, conversation_id=mine.conversation_id)
	assert theirs.conversation_id != mine.conversation_id
	assert len(conversation(mine.conversation_id, client_id=ME, db=db).messages) == 1


def test_long_first_question_becomes_short_title() -> None:
	assert history.title_from("  1소대   미편성 인원  ") == "1소대 미편성 인원"
	title = history.title_from("가" * 60)
	assert len(title) == history.TITLE_LENGTH + 1 and title.endswith("…")


def test_log_records_how_each_question_was_handled(monkeypatch) -> None:
	db = make_session()
	seed(db)

	answered = ask(db, "0년차 편성된 사람 빼줘")
	row = logged(db, answered.trace_id)
	assert (row.routed_by, row.tool, row.outcome, row.used_context) == ("rule", "propose_release", "answered", False)
	assert json.loads(row.args_json) == {"service_year": 0}
	assert row.latency_ms >= 0

	asked_back = ask(db, "재편성해줘")
	assert logged(db, asked_back.trace_id).outcome == "asked_back"

	from_context = ask(db, "저 인원들 편성 해제해줘", context=ChatContext(label="고른 명단", ids=["0-1"]))
	assert logged(db, from_context.trace_id).used_context is True

	def llm_off(message):
		raise llm.LLMUnavailable("꺼짐")

	monkeypatch.setattr(llm, "choose_tool", llm_off)
	missed = ask(db, "해군 빼고 교육 미달자 보여줘")
	row = logged(db, missed.trace_id)
	assert (row.routed_by, row.outcome, json.loads(row.unparsed_json)) == ("none", "not_understood", ["빼고"])


def test_tool_error_is_logged_and_still_raised(monkeypatch) -> None:
	db = make_session()
	seed(db)
	from user.app.copilot import tools

	def broken(db, args):
		raise RuntimeError("boom")

	monkeypatch.setitem(tools.TOOLS, "summarize_status", dataclasses.replace(tools.TOOLS["summarize_status"], run=broken))
	with pytest.raises(RuntimeError):
		ask(db, "오늘 현황")
	row = db.scalars(select(CopilotMessage)).one()
	assert (row.question, row.outcome) == ("오늘 현황", "error")


def test_answer_still_returns_when_saving_fails(monkeypatch) -> None:
	db = make_session()
	seed(db)

	def broken(*args, **kwargs):
		raise RuntimeError("disk full")

	monkeypatch.setattr(history, "save_turn", broken)
	response = ask(db, "오늘 현황")
	assert response.message and response.conversation_id is None


def test_approval_is_shown_on_reopen_and_cannot_run_twice() -> None:
	db = make_session()
	seed(db)
	response = ask(db, "0년차 편성된 사람 빼줘")
	request = ApplyRequest(kind="release", trace_id=response.trace_id, person_ids=["0-1"])

	assert apply(request, db).message == "1명의 편성을 해제했습니다."
	opened = conversation(response.conversation_id, client_id=ME, db=db)
	assert opened.messages[0].applied_at is not None
	assert opened.messages[0].applied_summary == "1명의 편성을 해제했습니다."
	assert conversations(client_id=ME, db=db)[0].changes == 1

	with pytest.raises(HTTPException) as error:
		apply(request, db)
	assert error.value.status_code == 409


def test_conversations_older_than_90_days_are_deleted() -> None:
	from datetime import timedelta

	db = make_session()
	seed(db)
	old = ask(db, "오늘 현황")
	recent = ask(db, "최근 변경 기록")
	db.get(CopilotConversation, old.conversation_id).updated_at -= timedelta(days=91)
	db.get(CopilotConversation, recent.conversation_id).updated_at -= timedelta(days=89)
	db.commit()

	ask(db, "이상 데이터 점검해줘")  # 새 대화를 시작할 때 정리한다
	assert db.get(CopilotConversation, old.conversation_id) is None
	assert db.scalars(select(CopilotMessage).where(CopilotMessage.trace_id == old.trace_id)).first() is None
	assert db.get(CopilotConversation, recent.conversation_id) is not None


def test_deleting_a_conversation_removes_it_but_keeps_the_change_log() -> None:
	from user.app.models.audit_log import AuditLog

	db = make_session()
	seed(db)
	response = ask(db, "0년차 편성된 사람 빼줘")
	apply(ApplyRequest(kind="release", trace_id=response.trace_id, person_ids=["0-1"]), db)
	kept = ask(db, "오늘 현황")
	logs = db.scalars(select(AuditLog)).all()
	assert logs

	with pytest.raises(HTTPException) as error:  # 다른 브라우저는 못 지운다
		delete_conversation(response.conversation_id, client_id=OTHER, db=db)
	assert error.value.status_code == 404

	delete_conversation(response.conversation_id, client_id=ME, db=db)
	assert [item.id for item in conversations(client_id=ME, db=db)] == [kept.conversation_id]
	assert db.scalars(select(CopilotMessage).where(CopilotMessage.trace_id == response.trace_id)).first() is None
	assert len(db.scalars(select(AuditLog)).all()) == len(logs)  # 변경 기록은 그대로

def test_questions_without_browser_id_are_still_logged() -> None:
	db = make_session()
	seed(db)
	response = ask(db, "오늘 현황", client_id=None)
	assert logged(db, response.trace_id).question == "오늘 현황"
	assert db.get(CopilotConversation, response.conversation_id).owner is None
