from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.api.transfers import submit_transfer_intake
from user.app.copilot import llm
from user.app.copilot.router import chat
from user.app.copilot.rules import Unparsed, route
from user.app.copilot.schemas import ChatRequest
from user.app.copilot.tools import SearchMembersArgs, TransferSquadArgs
from user.app.models.assignment import Assignment
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.schemas.transfer_intake import TransferIntakeCreate, TransferPersonDetails


def make_session() -> Session:
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	return Session(engine)


def add_person(db: Session, number: str, rank: str, squad_id: int | None, branch: str = "육군", registration_type: str | None = None) -> None:
	db.add(Person(
		military_number=number, name=number, branch=branch, rank=rank, service_year=5,
		position="소총수", mobilization_status="해당없음", status="active",
		squad_id=squad_id, registration_type=registration_type,
	))


def seed(db: Session) -> None:
	db.add_all([Squad(id=1, name="1소대 1분대"), Squad(id=2, name="1분대"), Squad(id=3, name="2분대"), Squad(id=4, name="1소대 2분대")])
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		OrganizationNode(id=10, parent_id=1, kind="platoon", name="1소대"),
		OrganizationNode(id=11, parent_id=10, kind="squad", name="1분대", squad_id=1, planned_strength=11),
		OrganizationNode(id=12, parent_id=10, kind="squad", name="2분대", squad_id=4, planned_strength=11),
		OrganizationNode(id=20, parent_id=1, kind="platoon", name="4소대"),
		OrganizationNode(id=21, parent_id=20, kind="squad", name="1분대", squad_id=2, planned_strength=11),
		OrganizationNode(id=22, parent_id=20, kind="squad", name="2분대", squad_id=3, planned_strength=11),
	])
	add_person(db, "26-0001", "하사", 1)
	add_person(db, "26-0002", "병장", 1)
	add_person(db, "26-0003", "중위", 2)
	add_person(db, "26-0004", "하사", 3, branch="해군")
	add_person(db, "26-0101", "하사", None, registration_type="예비군 전입")
	db.commit()


def ids(response, action_type: str = "filter") -> list[str]:
	return next(action.ids for action in response.ui_actions if action.type == action_type)


# ------------------------------------------------------------------ rules

def test_rules_parse_search_conditions() -> None:
	name, args = route("1소대 육군 간부 보여줘")
	assert name == "search_members"
	assert args == SearchMembersArgs(platoon="1소대", branch="육군", category="간부")

	name, args = route("미편성 전입자 명단")
	assert args == SearchMembersArgs(assigned=False, transfer_only=True)

	name, args = route("해병대 병장 몇 명이야")
	assert args == SearchMembersArgs(branch="해병대", rank="병장")


def test_rules_understand_unassigned_synonyms() -> None:
	unassigned_soldiers = ("search_members", SearchMembersArgs(category="병사", assigned=False))
	assert route("미지정 병사들 보여줘") == unassigned_soldiers
	assert route("편성 부대 미지정 병사들 보여줘") == unassigned_soldiers
	assert route("부대 없는 병사 보여줘") == unassigned_soldiers
	assert route("편성되지 않은 병사 명단") == unassigned_soldiers


def test_rules_leave_unparsed_negation_to_llm() -> None:
	# 부정 조건을 빠뜨리고 전체 병사를 보여주는 대신 LLM에 넘긴다.
	assert route("보류 안 된 병사 보여줘") == Unparsed(["보류", "안", "된"])
	assert route("해군 빼고 병사 보여줘") == Unparsed(["빼고"])


def test_rules_route_transfer_questions() -> None:
	assert route("방금 등록한 전입자 어디 편성하면 돼?") == ("recommend_squad_for_transfer", TransferSquadArgs())
	assert route("26-TEST-003 분대 추천해줘") == (
		"recommend_squad_for_transfer", TransferSquadArgs(military_number="26-TEST-003"),
	)


def test_rules_leave_unknown_requests_to_llm() -> None:
	assert route("안녕") is None
	assert route("내일 날씨 알려줘") == Unparsed(["내일", "날씨"])


# ---------------------------------------------------------- search_members

def test_search_platoon_uses_organization_tree() -> None:
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="4소대 간부 보여줘"), db)

	assert response.routed_by == "rule"
	assert ids(response) == ["26-0003", "26-0004"]
	assert response.ui_actions[0].type == "navigate"


def test_search_unassigned_drops_platoon_condition() -> None:
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="1소대 미편성자 보여줘"), db)

	assert ids(response) == ["26-0101"]
	assert "'1소대' 조건은 뺐어요" in response.message


def test_search_unknown_platoon_is_reported() -> None:
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="9소대 인원 보여줘"), db)

	assert response.ui_actions == []
	assert "9소대" in response.message


def test_reservists_api_supports_new_filters() -> None:
	from user.app.api.reservists import list_reservists

	db = make_session()
	seed(db)
	common = dict(query_text=None, branch=None, rank=None, status=None, mobilization_status=None, db=db)

	assert [p.military_number for p in list_reservists(**common, platoon="1소대", category=None, assigned=None)] == ["26-0001", "26-0002"]
	assert [p.military_number for p in list_reservists(**common, platoon=None, category="병사", assigned=None)] == ["26-0002"]
	assert [p.military_number for p in list_reservists(**common, platoon=None, category=None, assigned=False)] == ["26-0101"]


# ---------------------------------------------- recommend_squad_for_transfer

def test_unassigned_transfer_gets_proposal_without_db_change() -> None:
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="방금 등록한 전입자 어디 편성하면 돼?"), db)

	assert response.proposal is not None
	assert response.proposal.person_id == "26-0101"
	assert response.proposal.options[0].squad_name.endswith("분대")
	assert db.get(Person, "26-0101").squad_id is None
	assert db.scalars(select(Assignment)).all() == []


def test_pending_transfer_preview_names_auto_assigned_squad() -> None:
	db = make_session()
	seed(db)
	submit_transfer_intake(TransferIntakeCreate(person=TransferPersonDetails(
		military_number="26-70000099", name="대기전입", branch="해군", rank="하사",
		service_year=5, position="소총수", mobilization_status="해당없음",
	)), db)

	response = chat(ChatRequest(message="방금 등록한 전입자 어디 편성돼?"), db)

	assert response.proposal is None
	# 빈 분대(1소대 2분대)가 인원 수가 가장 적어 1순위, 해군 부사관 분대(4소대 2분대)가 다음
	assert "1순위인 1소대 2분대" in response.message
	assert "4소대 2분대" in response.message
	assert ids(response, "highlight") == ["26-70000099"]
	assert db.get(Person, "26-70000099") is None


def test_assigned_person_gets_move_card() -> None:
	"""이미 편성된 사람에게 편성을 물으면 막다른 답 대신 다른 분대로 옮기는 카드를 준다."""
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="26-0003 어디 편성해?"), db)

	assert "지금 4소대 1분대에 있어요" in response.message
	assert response.proposal.kind == "move"
	assert 2 not in [option.squad_id for option in response.proposal.options]  # 지금 분대는 후보가 아니다


# ------------------------------------------------------------------ llm

def test_llm_fallback_validates_arguments(monkeypatch) -> None:
	db = make_session()
	seed(db)
	monkeypatch.setattr(llm, "choose_tool", lambda message: ("search_members", {"branch": "해군"}))

	response = chat(ChatRequest(message="바다 쪽 사람들 좀"), db)

	assert response.routed_by == "llm"
	assert ids(response) == ["26-0004"]


def test_llm_bad_arguments_ask_again(monkeypatch) -> None:
	db = make_session()
	seed(db)
	monkeypatch.setattr(llm, "choose_tool", lambda message: ("search_members", {"branch": "우주군"}))

	response = chat(ChatRequest(message="이상한 요청"), db)

	assert response.ui_actions == []
	assert "다시 말씀해 주세요" in response.message


def test_llm_refuses_non_internal_host(monkeypatch) -> None:
	monkeypatch.setattr(llm, "OLLAMA_HOST", "https://ollama.com")
	try:
		llm.choose_tool("아무거나")
	except llm.LLMUnavailable as error:
		assert "내부 주소" in str(error)
	else:
		raise AssertionError("external host must be refused")


def test_josa_follows_final_consonant() -> None:
	from user.app.copilot.tools import josa

	assert josa("2소대 해군 병사", "은", "는") == "는"
	assert josa("미편성 인원", "은", "는") == "은"
	assert josa("윤대위", "과", "와") == "와"


# ------------------------------------------------- 이름 지정 / 일괄 편성

def test_rules_route_single_person_and_bulk_assignment() -> None:
	from user.app.copilot.tools import BulkAssignmentArgs

	assert route("황성민 어디에 편성해?") == ("recommend_squad_for_transfer", TransferSquadArgs(name="황성민"))
	assert route("어디에 편성해?") == ("recommend_squad_for_transfer", TransferSquadArgs())
	assert route("미편성 인원들 편성해줘") == ("propose_bulk_assignment", BulkAssignmentArgs())
	assert route("해군 전입자들 다 배치해줘") == (
		"propose_bulk_assignment", BulkAssignmentArgs(branch="해군", transfer_only=True),
	)
	assert route("미배정 인원 보여줘")[0] == "search_members"


def test_name_lookup_strips_particle_and_proposes() -> None:
	db = make_session()
	seed(db)
	db.add(Person(military_number="26-0200", name="황성민", branch="육군", rank="하사", service_year=5,
		position="소총수", mobilization_status="해당없음", status="active"))
	db.commit()

	response = chat(ChatRequest(message="황성민은 어디 편성해?"), db)

	assert response.proposal is not None
	assert response.proposal.kind == "assign_squad"
	assert response.proposal.person_id == "26-0200"


def test_bulk_assignment_plans_without_saving() -> None:
	db = make_session()
	seed(db)
	db.add(Person(military_number="26-0300", name="연차없음", branch="육군", rank="하사", service_year=None,
		position="소총수", mobilization_status="해당없음", status="active"))
	db.commit()

	response = chat(ChatRequest(message="미편성 인원들 편성해줘"), db)

	assert response.proposal is not None
	assert response.proposal.kind == "assign_bulk"
	assert [(item.person_id, item.squad_name) for item in response.proposal.assignments] == [("26-0101", "1소대 2분대")]
	assert response.proposal.notes == ["제외 1명: 편성 대상 아님 (연차 미등록)"]
	assert db.get(Person, "26-0101").squad_id is None
	assert db.scalars(select(Assignment)).all() == []


def test_bulk_plan_respects_capacity_and_groups() -> None:
	from user.app.services.organization import plan_vacancies

	db = make_session()
	db.add_all([Squad(id=1, name="가득 찬 분대"), Squad(id=2, name="빈 분대"), Squad(id=3, name="해군 분대")])
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		*(OrganizationNode(id=10 + squad_id, parent_id=1, kind="squad", name=f"{squad_id}분대",
			squad_id=squad_id, planned_strength=11) for squad_id in (1, 2, 3)),
	])
	for index in range(11):
		add_person(db, f"26-1{index:03d}", "병장", 1)
	add_person(db, "26-2000", "병장", 3, branch="해군")
	add_person(db, "26-3000", "병장", None)
	add_person(db, "26-3001", "병장", None, branch="해군")
	db.commit()

	plan = plan_vacancies(db, 1, db.scalars(select(Person).where(Person.squad_id.is_(None))).all())

	assert {person.military_number: squad_id for person, squad_id in plan["planned"]} == {"26-3000": 2, "26-3001": 3}


def test_bulk_assignment_excludes_zero_year() -> None:
	db = make_session()
	seed(db)
	db.add(Person(military_number="26-0400", name="영년차", branch="육군", rank="하사", service_year=0,
		position="소총수", mobilization_status="해당없음", status="active"))
	db.commit()

	response = chat(ChatRequest(message="미편성 인원들 편성해줘"), db)

	assert "26-0400" not in [item.person_id for item in response.proposal.assignments]
	assert "제외 1명: 편성 대상 아님 (0년차는 편성 대상 아님)" in response.proposal.notes


# ------------------------------------------------- 직전 명단 이어받기

def test_follow_up_with_single_person_list_proposes_that_person() -> None:
	from user.app.copilot.schemas import ChatContext

	db = make_session()
	seed(db)
	add_person(db, "26-0102", "하사", None)  # 전입자가 아닌 미편성자: 명단 밖
	db.commit()

	first = chat(ChatRequest(message="미편성 전입자 명단"), db)
	context = ChatContext(label=first.ui_actions[-1].label, ids=ids(first))
	response = chat(ChatRequest(message="저 인원들 자동으로 편성해줘", context=context), db)

	assert context.ids == ["26-0101"]
	assert response.proposal is not None
	assert response.proposal.kind == "assign_squad"
	assert response.proposal.person_id == "26-0101"


def test_follow_up_bulk_excludes_people_outside_context() -> None:
	from user.app.copilot.schemas import ChatContext

	db = make_session()
	seed(db)
	add_person(db, "26-0102", "하사", None, registration_type="예비군 전입")
	add_person(db, "26-0103", "하사", None)
	db.commit()

	context = ChatContext(label="전입자 미편성 인원", ids=["26-0101", "26-0102", "26-0001"])
	response = chat(ChatRequest(message="저 인원들 자동으로 편성해줘", context=context), db)

	assert response.proposal is not None and response.proposal.kind == "assign_bulk"
	assert sorted(item.person_id for item in response.proposal.assignments) == ["26-0101", "26-0102"]
	assert "전입자 미편성 인원 2명 중 2명" in response.message
	assert "이미 편성된 1명" in response.message


def test_follow_up_without_context_asks_instead_of_using_everyone() -> None:
	db = make_session()
	seed(db)

	response = chat(ChatRequest(message="저 인원들 자동으로 편성해줘"), db)

	assert response.proposal is None
	assert "어떤 인원" in response.message


def test_reference_detection() -> None:
	from user.app.copilot.rules import refers_to_previous

	assert refers_to_previous("저 인원들 자동으로 편성해줘")
	assert refers_to_previous("그 사람 어디 편성해?")
	assert refers_to_previous("이들 다 배치해줘")
	assert not refers_to_previous("미편성 인원들 편성해줘")
	assert not refers_to_previous("황성민이 분대 어디야")
