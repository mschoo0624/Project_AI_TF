"""Copilot 되돌리기: 승인한 편성·해제·재편성을 미리 보고 되돌린다. 이후 바뀐 인원은 건너뛴다."""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.copilot.router import apply, chat, conversation, conversations, preview_undo, undo
from user.app.copilot.schemas import ApplyRequest, AssignmentSelection, ChatRequest, UndoRequest
from user.app.models.assignment import Assignment
from user.app.models.audit_log import AuditLog
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.assignment import reassign_person

ME = "browser-aaaa1111"
OTHER = "browser-bbbb2222"


def make_session() -> Session:
	engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	return Session(engine)


def add_person(db: Session, number: str, squad_id: int | None, service_year: int = 5, branch: str = "육군") -> None:
	db.add(Person(military_number=number, name=f"이름{number}", branch=branch, rank="병장", service_year=service_year,
		position="소총수", mobilization_status="동원지정" if squad_id else "동원미지정", status="active", squad_id=squad_id))
	if squad_id is not None:
		db.add(Assignment(person_id=number, squad_id=squad_id, assigned_date=date.today(), status="assigned"))


def seed(db: Session) -> None:
	"""1소대 1·2분대. 1분대에 a·b, 미편성 u."""
	db.add_all([Squad(id=1, name="1분대"), Squad(id=2, name="2분대")])
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		OrganizationNode(id=10, parent_id=1, kind="platoon", name="1소대"),
		OrganizationNode(id=11, parent_id=10, kind="squad", name="1분대", squad_id=1, planned_strength=11),
		OrganizationNode(id=12, parent_id=10, kind="squad", name="2분대", squad_id=2, planned_strength=11),
	])
	add_person(db, "a", 1)
	add_person(db, "b", 1)
	add_person(db, "u", None)
	db.commit()


def approved(db: Session, question: str, request: ApplyRequest) -> str:
	"""질문해서 받은 trace_id로 승인까지 하고 trace_id를 돌려준다."""
	response = chat(ChatRequest(message=question, client_id=ME), db)
	apply(request.model_copy(update={"trace_id": response.trace_id}), db)
	return response.trace_id


def squad_of(db: Session, number: str) -> int | None:
	db.expire_all()
	return db.get(Person, number).squad_id


def test_undo_release_puts_people_back_after_preview() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "1소대 1분대 비워줘", ApplyRequest(kind="release", person_ids=["a", "b"]))
	assert squad_of(db, "a") is None

	preview = preview_undo(trace, client_id=ME, db=db)
	assert [(step.person_id, step.now, step.after) for step in preview.steps] == [
		("a", "미편성", "1소대 1분대"), ("b", "미편성", "1소대 1분대")]
	assert preview.skipped == []
	assert squad_of(db, "a") is None  # 미리 보기는 아무것도 바꾸지 않는다

	result = undo(trace, UndoRequest(client_id=ME), db)
	assert result.message == "2명을 되돌렸습니다."
	assert squad_of(db, "a") == 1 and squad_of(db, "b") == 1
	assert db.get(Person, "a").mobilization_status == "동원지정"
	assert db.scalars(select(Assignment).where(Assignment.person_id == "a")).one().squad_id == 1
	log = db.scalars(select(AuditLog).where(AuditLog.action == "undo")).one()
	assert (log.source, log.trace_id) == ("copilot", trace)

	# 대화를 다시 열면 되돌림이 보이고, 목록에도 표시된다.
	conversation_id = conversations(client_id=ME, db=db)[0].id
	message = conversation(conversation_id, client_id=ME, db=db).messages[0]
	assert message.undone_at is not None and message.undone_summary == "2명을 되돌렸습니다."
	assert conversations(client_id=ME, db=db)[0].undone == 1


def test_undo_assignment_releases_people() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "미편성 인원들 편성해줘",
		ApplyRequest(kind="assign_bulk", assignments=[AssignmentSelection(person_id="u", squad_id=2)]))
	assert squad_of(db, "u") == 2

	assert undo(trace, UndoRequest(client_id=ME), db).message == "1명을 되돌렸습니다."
	assert squad_of(db, "u") is None
	assert db.get(Person, "u").mobilization_status == "동원미지정"
	assert db.scalars(select(Assignment).where(Assignment.person_id == "u")).first() is None


def test_undo_move_returns_to_previous_squad() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "이름a 재편성해줘",
		ApplyRequest(kind="move", assignments=[AssignmentSelection(person_id="a", squad_id=2)]))
	assert squad_of(db, "a") == 2

	preview = preview_undo(trace, client_id=ME, db=db)
	assert [(step.now, step.after) for step in preview.steps] == [("1소대 2분대", "1소대 1분대")]
	undo(trace, UndoRequest(client_id=ME), db)
	assert squad_of(db, "a") == 1


def test_people_changed_afterwards_are_skipped_not_overwritten() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "1소대 1분대 비워줘", ApplyRequest(kind="release", person_ids=["a", "b"]))
	# 그사이 화면에서 b를 2분대에 편성했다.
	db.add(Assignment(person_id="b", squad_id=2, assigned_date=date.today(), status="assigned"))
	db.get(Person, "b").squad_id = 2
	db.commit()

	preview = preview_undo(trace, client_id=ME, db=db)
	assert [step.person_id for step in preview.steps] == ["a"]
	assert [(item.person_id, item.reason) for item in preview.skipped] == [("b", "이후 다시 바뀜 (지금 1소대 2분대)")]

	result = undo(trace, UndoRequest(client_id=ME), db)
	assert result.message == "1명을 되돌렸습니다. 1명은 건너뛰었습니다."
	assert squad_of(db, "a") == 1 and squad_of(db, "b") == 2  # b의 이후 변경은 그대로


def test_moved_again_on_screen_is_skipped() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "이름a 재편성해줘",
		ApplyRequest(kind="move", assignments=[AssignmentSelection(person_id="a", squad_id=2)]))
	reassign_person(db, "a", 1)  # 화면에서 다시 옮김

	with pytest.raises(HTTPException) as error:
		undo(trace, UndoRequest(client_id=ME), db)
	assert error.value.status_code == 400
	assert "되돌릴 수 있는 인원이 없습니다" in error.value.detail
	assert squad_of(db, "a") == 1


def test_undo_restores_exactly_even_past_assignment_rules() -> None:
	"""되돌리기는 새 편성이 아니다. 0년차·정원 규칙에 걸려도 승인 전 상태로 돌려놓는다."""
	db = make_session()
	seed(db)
	add_person(db, "z", 1, service_year=0)  # 예전에 잘못 편성된 0년차
	db.commit()
	trace = approved(db, "1소대 1분대 비워줘", ApplyRequest(kind="release", person_ids=["a", "b", "z"]))
	db.get(OrganizationNode, 11).planned_strength = 1  # 이제 1분대 정원은 1명
	db.commit()

	preview = preview_undo(trace, client_id=ME, db=db)
	assert sorted(step.person_id for step in preview.steps) == ["a", "b", "z"]
	assert preview.skipped == []
	assert undo(trace, UndoRequest(client_id=ME), db).message == "3명을 되돌렸습니다."
	assert [squad_of(db, number) for number in ("a", "b", "z")] == [1, 1, 1]


def test_partly_undone_change_can_be_finished() -> None:
	"""예전 규칙으로 일부만 되돌린 변경은 남은 인원만 마저 되돌린다."""
	import json

	from user.app.copilot import history

	db = make_session()
	seed(db)
	trace = approved(db, "1소대 1분대 비워줘", ApplyRequest(kind="release", person_ids=["a", "b"]))
	# a만 되돌린 상태를 만든다.
	db.get(Person, "a").squad_id = 1
	db.add(AuditLog(action="undo", trace_id=trace, summary="되돌리기 1명",
		detail=json.dumps([{"military_number": "a", "name": "a", "squad_id": 1}])))
	history.mark_undone(db, history._message(db, trace), "1명을 되돌렸습니다. 1명은 건너뛰었습니다.")

	preview = preview_undo(trace, client_id=ME, db=db)
	assert [step.person_id for step in preview.steps] == ["b"]
	assert undo(trace, UndoRequest(client_id=ME), db).message == "남은 1명을 마저 되돌렸습니다."
	assert squad_of(db, "a") == 1 and squad_of(db, "b") == 1

	with pytest.raises(HTTPException) as error:
		undo(trace, UndoRequest(client_id=ME), db)
	assert (error.value.status_code, error.value.detail) == (409, "이미 되돌린 변경입니다.")


def test_undo_once_only_and_only_by_owner() -> None:
	db = make_session()
	seed(db)
	trace = approved(db, "1소대 1분대 비워줘", ApplyRequest(kind="release", person_ids=["a", "b"]))

	with pytest.raises(HTTPException) as error:
		preview_undo(trace, client_id=OTHER, db=db)
	assert error.value.status_code == 404

	undo(trace, UndoRequest(client_id=ME), db)
	with pytest.raises(HTTPException) as error:
		undo(trace, UndoRequest(client_id=ME), db)
	assert (error.value.status_code, error.value.detail) == (409, "이미 되돌린 변경입니다.")


def test_cannot_undo_proposal_that_was_not_approved() -> None:
	db = make_session()
	seed(db)
	response = chat(ChatRequest(message="1소대 1분대 비워줘", client_id=ME), db)
	with pytest.raises(HTTPException) as error:
		preview_undo(response.trace_id, client_id=ME, db=db)
	assert error.value.status_code == 409
