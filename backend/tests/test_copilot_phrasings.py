"""문장 → 규칙 해석 표. 사용자가 보고한 문장은 여기에 한 줄씩 추가해 같은 버그가 돌아오지 않게 한다.

기대값: (도구 이름, 조건 dict) / Unparsed([...]) / None(규칙 대상 아님 → LLM)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.copilot import llm
from user.app.copilot.router import chat
from user.app.copilot.rules import Unparsed, route
from user.app.copilot.schemas import ChatContext, ChatRequest
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad

S, B, R = "search_members", "propose_bulk_assignment", "propose_release"

PHRASINGS = [
	# 검색
	("1소대 육군 간부 보여줘", (S, {"platoon": "1소대", "branch": "육군", "category": "간부"})),
	("미편성 전입자 명단", (S, {"assigned": False, "transfer_only": True})),
	("해병대 병장 몇 명이야", (S, {"branch": "해병대", "rank": "병장"})),
	("간부들은 누구야", (S, {"category": "간부"})),
	("1소대의 병사들 보여줘", (S, {"platoon": "1소대", "category": "병사"})),
	# 보고된 버그: 미지정을 몰라서 병사 전체를 보여줬다
	("미지정 병사들 보여줘", (S, {"category": "병사", "assigned": False})),
	("편성 부대 미지정 병사들 보여줘", (S, {"category": "병사", "assigned": False})),
	("부대 없는 병사 보여줘", (S, {"category": "병사", "assigned": False})),
	("배정 안 된 해군 보여줘", (S, {"branch": "해군", "assigned": False})),
	# 보고된 버그: 숫자 없는 '소대'를 몰라서 '이해하지 못했어요'만 답했다
	("소대 없는 인원 보여줘", (S, {"assigned": False})),
	("소대 미편성 인원 보여줘", (S, {"assigned": False})),
	("소대에 편성 안 된 인원 보여줘", (S, {"assigned": False})),
	("1소대 미편성 인원 보여줘", (S, {"platoon": "1소대", "assigned": False})),
	("1소대 편성 안 된 인원 보여줘", (S, {"platoon": "1소대", "assigned": False})),
	("소대 인원 보여줘", Unparsed(["소대"], "몇 소대인지 숫자로 함께 말씀해 주세요. 예: \"1소대 인원 보여줘\"")),
	("분대 인원 보여줘", Unparsed(["분대"], "몇 분대인지 숫자로 함께 말씀해 주세요. 예: \"1소대 3분대 인원 보여줘\"")),
	# 교육 미달·고발 (검색에 합쳐짐)
	("올해 교육 시간 못 채운 사람", (S, {"training": "shortfall"})),
	("1소대 병사 훈련 미이수자", (S, {"platoon": "1소대", "category": "병사", "training": "shortfall"})),
	# 보고된 버그: 교육 미달 도구가 미편성 조건을 버렸다
	("교육 미달자 중에서 편성 부대가 없는 인원들 보여줘", (S, {"assigned": False, "training": "shortfall"})),
	("편성된 인원 중 교육 미이수자", (S, {"assigned": True, "training": "shortfall"})),
	("고발 대상자 중 해군", (S, {"branch": "해군", "training": "prosecution"})),
	# 편성 해제
	("0년차 편성된 사람 빼줘", (R, {"service_year": 0})),
	("1소대 0년차 편성 해제해줘", (R, {"platoon": "1소대", "service_year": 0})),
	("편성 대상 아닌 사람 편성 해제해줘", (R, {"not_assignable": True})),
	# 일괄 편성: 조건이 섞여도 된다
	("미편성 인원들 편성해줘", (B, {})),
	("해군 전입자들 다 배치해줘", (B, {"branch": "해군", "transfer_only": True})),
	("미편성 병사 중 교육 미달자 편성해줘", (B, {"category": "병사", "training": "shortfall"})),
	("이들 다 배치해줘", (B, {})),
	# 보고된 버그: 재편성을 몰라서 "이미 편성돼 있어요"로 끝나거나, 띄어 쓴 "편성 해주세요"가 AI로 새서 엉뚱한 검색이 됐다
	("정태윤은 1소대에 있으면 안돼. 재편성해줘", ("propose_move", {"name": "정태윤은", "avoid_platoon": "1소대"})),
	("정태윤 이병 다른 소대로 편성 해주세요", ("propose_move", {"name": "정태윤", "other_platoon": True})),
	("정태윤 1소대 말고 다른 데로 옮겨줘", ("propose_move", {"name": "정태윤", "avoid_platoon": "1소대"})),
	("재편성해줘", ("propose_move", {})),
	("정태윤 이병 자동편성 해주세요", ("recommend_squad_for_transfer", {"name": "정태윤"})),
	("미편성 인원들 편성 해주세요", (B, {})),
	# 보고된 버그: 이름을 몰라서 "정태윤 편성 해제해줘"가 '정태윤'을 이해 못 한 말로 남겼다
	("정태윤 편성 해제해줘", (R, {"name": "정태윤"})),
	("정태윤은 편성에서 빼줘", (R, {"name": "정태윤"})),
	("정태윤 이병 보여줘", (S, {"rank": "이병", "name": "정태윤"})),
	# 이해 못 한 말이 남으면 답하지 않는다
	("해군 빼고 병사 보여줘", Unparsed(["빼고"])),
	("보류 안 된 병사 보여줘", Unparsed(["보류", "안", "된"])),
	("교육 미달자 중 운전병 보여줘", Unparsed(["운전병"])),
	("작년 미편성 인원 보여줘", Unparsed(["작년"])),
	# 규칙 대상 아님
	("안녕", None),
	("인원 보여줘", None),
]


@pytest.mark.parametrize(("message", "expected"), PHRASINGS, ids=[message for message, _ in PHRASINGS])
def test_phrasing(message, expected) -> None:
	routed = route(message)
	if isinstance(expected, tuple):
		assert routed is not None and not isinstance(routed, Unparsed), routed
		assert (routed[0], routed[1].model_dump(exclude_defaults=True)) == expected
	else:
		assert routed == expected


# ------------------------------------------------------------- 응답에서 확인

def make_session() -> Session:
	engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	db = Session(engine)
	db.add_all([Squad(id=1, name="1분대")])
	db.add_all([
		OrganizationNode(id=1, kind="root", name="전투편성"),
		OrganizationNode(id=10, parent_id=1, kind="platoon", name="1소대"),
		OrganizationNode(id=11, parent_id=10, kind="squad", name="1분대", squad_id=1, planned_strength=11),
	])
	for number, branch, year, squad in (("a", "육군", 5, 1), ("b", "해군", 5, None), ("c", "육군", 0, 1), ("d", "육군", 5, None)):
		db.add(Person(military_number=number, name=number, branch=branch, rank="병장", service_year=year,
			position="소총수", mobilization_status="동원미지정", status="active", squad_id=squad))
	db.commit()
	return db


def test_answer_shows_applied_conditions() -> None:
	db = make_session()
	response = chat(ChatRequest(message="미편성 병사 교육 미달자 보여줘"), db)
	assert response.conditions == ["미편성", "병사", "교육 미달"]


def test_unparsed_without_llm_names_the_words(monkeypatch) -> None:
	def unavailable(message):
		raise llm.LLMUnavailable("꺼져 있음")

	monkeypatch.setattr(llm, "choose_tool", unavailable)
	response = chat(ChatRequest(message="해군 빼고 병사 보여줘"), make_session())
	assert response.unparsed == ["빼고"]
	assert response.message.startswith("'빼고'는 아직 조건으로 이해하지 못했어요.")
	assert response.ui_actions == []  # 조건을 빼고 명단을 보여주지 않는다


def test_release_by_name() -> None:
	db = make_session()
	db.add(Person(military_number="26-9", name="정태윤", branch="육군", rank="이병", service_year=1,
		position="행정병", mobilization_status="동원지정", status="active", squad_id=1))
	db.commit()
	response = chat(ChatRequest(message="정태윤 편성 해제해줘"), db)
	assert response.conditions == ["편성된", "'정태윤'"]
	assert [item.person_id for item in response.proposal.assignments] == ["26-9"]
	assert response.message.startswith("편성된 '정태윤' 1명")
	assert chat(ChatRequest(message="정태윤 보여줘"), db).message.startswith("'정태윤'은 1명")


def test_bare_platoon_is_asked_back_without_llm(monkeypatch) -> None:
	def must_not_call(message):
		raise AssertionError("숫자 없는 소대는 LLM에 넘기지 않는다")

	monkeypatch.setattr(llm, "choose_tool", must_not_call)
	response = chat(ChatRequest(message="소대 인원 보여줘"), make_session())
	assert response.message.startswith("몇 소대인지")
	assert response.ui_actions == []


def test_follow_up_keeps_conditions_said_with_reference() -> None:
	db = make_session()
	context = ChatContext(label="1분대", ids=["a", "c"])
	response = chat(ChatRequest(message="저 인원들 중 0년차 편성 해제해줘", context=context), db)
	assert [item.person_id for item in response.proposal.assignments] == ["c"]
