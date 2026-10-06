"""Copilot: 편성 해제, 빈자리 부족 안내, 변경 기록, 이상 데이터, 현황, 개인 요약, 교육 미달."""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.copilot.insights import PersonSummaryArgs, StatusArgs
from user.app.copilot.router import apply, chat
from user.app.copilot.rules import Unparsed, route
from user.app.copilot.schemas import ApplyRequest, ChatRequest
from user.app.copilot.tools import ReleaseArgs, SearchMembersArgs
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.training import all_training_progress
from user.app.services.training_summary import current_year_hours


def make_session() -> Session:
	engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	return Session(engine)


def add_person(db: Session, number: str, rank: str = "병장", squad_id: int | None = None, branch: str = "육군",
		service_year: int = 5, status: str = "active", name: str | None = None) -> Person:
	person = Person(military_number=number, name=name or number, branch=branch, rank=rank, service_year=service_year,
		position="소총수", mobilization_status="동원지정" if squad_id else "동원미지정", status=status, squad_id=squad_id)
	db.add(person)
	return person


def seed(db: Session) -> None:
	"""1소대(1·2분대), 2소대(1분대). 분대 정원 11명."""
	db.add_all([Squad(id=1, name="1분대"), Squad(id=2, name="2분대"), Squad(id=3, name="1분대")])
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		OrganizationNode(id=10, parent_id=1, kind="platoon", name="1소대"),
		OrganizationNode(id=11, parent_id=10, kind="squad", name="1분대", squad_id=1, planned_strength=11),
		OrganizationNode(id=12, parent_id=10, kind="squad", name="2분대", squad_id=2, planned_strength=11),
		OrganizationNode(id=20, parent_id=1, kind="platoon", name="2소대"),
		OrganizationNode(id=21, parent_id=20, kind="squad", name="1분대", squad_id=3, planned_strength=11),
	])
	db.commit()


def ask(db: Session, message: str):
	return chat(ChatRequest(message=message), db)


# ------------------------------------------------------------------ rules

def test_rules_route_new_requests() -> None:
	assert route("0년차 편성된 사람 빼줘") == ("propose_release", ReleaseArgs(service_year=0))
	assert route("1소대 3분대 비워줘") == ("propose_release", ReleaseArgs(platoon="1소대", squad="3분대"))
	assert route("편성 대상 아닌 사람 편성 해제해줘") == ("propose_release", ReleaseArgs(not_assignable=True))
	assert route("분대 추가해줘")[0] == "explain_squad_shortage"
	assert route("이상 데이터 점검해줘")[0] == "check_data_issues"
	assert route("최근 변경 기록")[0] == "show_recent_changes"
	assert route("오늘 현황")[0] == "summarize_status"
	assert route("보류자 몇 명이야") == ("summarize_status", StatusArgs(focus="보류"))
	assert route("홍길동 정보") == ("person_summary", PersonSummaryArgs(name="홍길동"))
	assert route("훈련병005 정보") == ("person_summary", PersonSummaryArgs(name="훈련병005"))
	assert route("1소대 병사 교육 미달자 보여줘") == (
		"search_members", SearchMembersArgs(platoon="1소대", category="병사", training="shortfall"),
	)
	assert route("고발 대상자 보여줘") == ("search_members", SearchMembersArgs(training="prosecution"))
	assert route("교육 미달자 중에서 편성 부대가 없는 인원들 보여줘") == (
		"search_members", SearchMembersArgs(assigned=False, training="shortfall"),
	)
	# 해석 못 한 부정 조건이 남으면 일반 검색으로도 새지 않고 LLM에 넘긴다.
	assert route("해군 빼고 교육 미달자 보여줘") == Unparsed(["빼고"])
	# 기존 편성 요청은 그대로
	assert route("미편성 인원들 편성해줘")[0] == "propose_bulk_assignment"


# ---------------------------------------------------------------- 편성 해제

def test_release_zero_year_then_apply_records_change() -> None:
	db = make_session()
	seed(db)
	add_person(db, "0-1", squad_id=1, service_year=0)
	add_person(db, "0-2", squad_id=3, service_year=0)
	add_person(db, "5-1", squad_id=1, service_year=5)
	db.commit()

	response = ask(db, "0년차 편성된 사람 빼줘")
	assert response.proposal.kind == "release"
	assert sorted(item.person_id for item in response.proposal.assignments) == ["0-1", "0-2"]
	assert db.get(Person, "0-1").squad_id == 1  # 제안만, 저장 안 함

	result = apply(ApplyRequest(kind="release", trace_id=response.trace_id,
		person_ids=[item.person_id for item in response.proposal.assignments]), db)
	assert result.message == "2명의 편성을 해제했습니다."
	assert db.get(Person, "0-1").squad_id is None
	assert db.get(Person, "0-1").mobilization_status == "동원미지정"
	assert db.get(Person, "5-1").squad_id == 1
	log = db.scalars(select(AuditLog)).one()
	assert (log.action, log.source, log.trace_id, log.summary) == ("release", "copilot", response.trace_id, "편성 해제 2명")


def test_release_ambiguous_squad_asks_platoon() -> None:
	db = make_session()
	seed(db)
	add_person(db, "a", squad_id=1)
	db.commit()

	assert "어느 소대" in ask(db, "1분대 비워줘").message
	response = ask(db, "1소대 1분대 비워줘")
	assert [item.person_id for item in response.proposal.assignments] == ["a"]


def test_release_follow_up_uses_previous_list() -> None:
	from user.app.copilot.schemas import ChatContext

	db = make_session()
	seed(db)
	add_person(db, "a", squad_id=1)
	add_person(db, "b", squad_id=1)
	db.commit()

	response = chat(ChatRequest(message="저 인원들 편성 해제해줘", context=ChatContext(label="고른 명단", ids=["a"])), db)
	assert [item.person_id for item in response.proposal.assignments] == ["a"]


# ---------------------------------------------------------------- 재편성

def test_move_out_of_mixed_squad_avoiding_platoon() -> None:
	"""1소대 1분대(해군 병사 분대)에 잘못 들어간 육군 병사를 1소대 밖으로 옮긴다."""
	db = make_session()
	seed(db)
	add_person(db, "navy", squad_id=1, branch="해군")
	add_person(db, "wrong", squad_id=1, name="정태윤")
	add_person(db, "army-1", squad_id=2)  # 1소대 2분대: 육군 병사 (1소대라 제외돼야 함)
	add_person(db, "army-2", squad_id=3)  # 2소대 1분대: 육군 병사
	db.commit()

	response = ask(db, "정태윤은 1소대에 있으면 안돼. 재편성해줘")
	assert response.proposal.kind == "move"
	assert [option.squad_id for option in response.proposal.options] == [3]
	assert db.get(Person, "wrong").squad_id == 1  # 제안만, 저장 안 함

	result = apply(ApplyRequest(kind="move", trace_id=response.trace_id,
		assignments=[{"person_id": "wrong", "squad_id": 3}]), db)
	assert "옮겼습니다" in result.message
	assert db.get(Person, "wrong").squad_id == 3
	log = db.scalars(select(AuditLog)).one()
	assert (log.action, log.source) == ("move", "copilot")


def test_move_without_room_explains_and_keeps_squad() -> None:
	db = make_session()
	seed(db)
	add_person(db, "wrong", squad_id=1, name="정태윤")
	for index in range(11):
		add_person(db, f"full-{index}", squad_id=3)
	db.add(Person(military_number="navy", name="navy", branch="해군", rank="병장", service_year=5,
		position="소총수", mobilization_status="동원지정", status="active", squad_id=2))
	db.commit()

	response = ask(db, "정태윤 다른 소대로 옮겨줘")
	assert response.proposal is None
	assert "옮길 수 있는 육군 병사 분대가 없어요" in response.message
	assert db.get(Person, "wrong").squad_id == 1


def test_apply_move_rejects_full_or_mixed_target() -> None:
	import pytest
	from fastapi import HTTPException

	db = make_session()
	seed(db)
	add_person(db, "wrong", squad_id=1)
	add_person(db, "navy", squad_id=2, branch="해군")
	db.commit()
	with pytest.raises(HTTPException):
		apply(ApplyRequest(kind="move", assignments=[{"person_id": "wrong", "squad_id": 2}]), db)
	assert db.get(Person, "wrong").squad_id == 1


def test_bare_move_uses_single_person_from_previous_answer() -> None:
	from user.app.copilot.schemas import ChatContext

	db = make_session()
	seed(db)
	add_person(db, "wrong", squad_id=1, name="정태윤")
	db.commit()
	response = chat(ChatRequest(message="재편성해줘", context=ChatContext(label="정태윤", ids=["wrong"])), db)
	assert response.proposal.kind == "move"
	assert response.proposal.person_id == "wrong"
	assert "누구를 재편성할지" in ask(db, "재편성해줘").message


# ---------------------------------------------------------------- 분대 추가 금지

def test_copilot_never_adds_squads() -> None:
	"""빈자리가 없으면 몇 개가 모자라는지만 안내하고, 분대는 편제 화면에서 사람이 직접 만든다."""
	db = make_session()
	seed(db)
	for squad_id in (1, 2, 3):
		for index in range(11):
			add_person(db, f"full{squad_id}-{index}", squad_id=squad_id)
	for index in range(12):
		add_person(db, f"new-{index:02d}", rank="하사")
	db.commit()

	response = ask(db, "미편성 인원들 편성해줘")
	assert response.proposal is None
	assert "분대가 약 2개 더 있어야" in response.message  # 육군 부사관 12명 → 11명 + 1명
	assert "편제 화면에서 분대를 직접 추가" in response.message

	response = ask(db, "분대 3개 추가해줘")
	assert response.proposal is None
	assert response.message.startswith("Copilot은 분대를 추가하지 않아요.")
	assert db.scalar(select(func.count()).select_from(Squad)) == 3
	assert db.scalar(select(func.count()).select_from(OrganizationNode)) == 6


# ---------------------------------------------------------------- 이상 데이터

def test_data_check_finds_wrong_assignments_and_mixed_squads() -> None:
	db = make_session()
	seed(db)
	add_person(db, "zero", squad_id=1, service_year=0)
	add_person(db, "army", squad_id=2)
	add_person(db, "navy", squad_id=2, branch="해군")
	db.commit()

	message = ask(db, "이상 데이터 점검해줘").message
	assert "편성 대상이 아닌데 편성됨 1명" in message
	assert "1소대 2분대: 육군 병사, 해군 병사" in message


# ---------------------------------------------------------------- 교육·현황·개인

def test_fast_training_hours_match_existing_progress() -> None:
	db = make_session()
	seed(db)
	people = [
		add_person(db, "y1", service_year=1),
		add_person(db, "y3", service_year=3, squad_id=1),
		add_person(db, "y5", service_year=5),
		add_person(db, "officer", rank="중위", service_year=4),
	]
	db.add_all([
		Education(person_id="y1", education_year=1, training_hours=10, attendance_status="completed"),
		Education(person_id="y3", education_year=2, training_hours=28, attendance_status="completed"),
		Education(person_id="y3", education_year=3, training_hours=0, attendance_status="unexcused_absence"),
		Education(person_id="y5", education_year=5, training_hours=20, attendance_status="completed"),
	])
	db.commit()

	fast = current_year_hours(db, people)
	for person in people:
		slow = all_training_progress(db, person)[person.service_year]
		item = fast[person.military_number]
		assert (item.required, item.completed, item.remaining) == (
			slow["required_hours"], slow["completed_hours"], slow["remaining_hours"]), person.military_number


def test_training_shortfall_status_and_person_summary() -> None:
	db = make_session()
	seed(db)
	add_person(db, "done", service_year=5, name="김완료")
	add_person(db, "short", service_year=5, name="이미달")
	# 지난 연차 미이수는 다음 연차로 이월되므로 1~5년차를 모두 채워 둔다.
	db.add_all(Education(person_id="done", education_year=year, training_hours=40, attendance_status="completed")
		for year in range(1, 6))
	db.commit()

	response = ask(db, "교육 미달자 보여줘")
	assert "교육 미달자는 1명" in response.message
	assert response.ui_actions[-1].ids == ["short"]

	assert "미달 1명" in ask(db, "오늘 현황").message

	add_person(db, "short-assigned", service_year=5, squad_id=1)
	db.commit()
	response = ask(db, "교육 미달자 중에서 편성 부대가 없는 인원들 보여줘")
	assert response.message.startswith("미편성 교육 미달자는 1명")
	assert response.ui_actions[-1].ids == ["short"]

	summary = ask(db, "이미달 정보").message
	assert "이미달(short)" in summary
	assert "0시간 이수" in summary and "이월" in summary


def test_recent_changes_lists_screen_and_copilot_changes() -> None:
	from user.app.services.assignment import confirm_assignment_selections

	db = make_session()
	seed(db)
	add_person(db, "a")
	db.commit()
	confirm_assignment_selections(db, [("a", 1)])

	message = ask(db, "최근 변경 기록").message
	assert "[화면] 편성 1명" in message
