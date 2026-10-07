"""Copilot tools: thin, read-only wrappers around existing services.

Nothing here writes to the DB. Proposals are returned as cards; the frontend
calls the existing write API only after the user clicks [승인].
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.common import TRANSFER_REGISTRATION, Tool, ToolResult, josa, squad_label
from user.app.copilot.filters import PersonFilter, resolve_people
from user.app.copilot.schemas import PlannedAssignment, Proposal, SquadOption, UiAction
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.transfer_intake import TransferIntake
from user.app.services.assignment import (
	is_assignable, not_assignable_reason, personnel_category, recommend_squads_for,
)
from user.app.services.organization import plan_vacancies, root_node_id
from user.app.services.person_search import squad_ids_for_platoon
from user.app.services.person_search import PersonSearch, search_people

# ---------------------------------------------------------------- search_members

class SearchMembersArgs(PersonFilter):
	"""조건은 PersonFilter 그대로. 교육 미달·고발 검토 대상 명단도 이 도구로 찾는다."""


def describe(condition: PersonFilter) -> str:
	return " ".join(condition.labels(with_training=False))


def _roster(label: str, ids: list[str]) -> list[UiAction]:
	return [UiAction(type="navigate", tab="roster", subtab="people"),
		UiAction(type="filter", tab="roster", label=label, ids=ids)]

# 명단 검색
def search_members(db: Session, args: SearchMembersArgs) -> ToolResult:
	resolved = resolve_people(db, args) # 대상 인원 찾기
	condition = resolved.applied or args
	chips = condition.labels()
	if resolved.question:
		return ToolResult(resolved.question, conditions=chips)
	notes = resolved.notes
	people = resolved.people
	ids = [person.military_number for person in people]
	label = describe(condition)

	if condition.training == "prosecution":
		title = f"{label} 고발 검토 대상".strip()
		if not people:
			return ToolResult(" ".join([*notes, f"{title}{josa(title, '이', '가')} 없어요."]), conditions=chips)
		counts: dict[str, int] = {}
		for reason in resolved.reasons.values():
			counts[reason] = counts.get(reason, 0) + 1
		detail = ", ".join(f"{reason} {count}명" for reason, count in sorted(counts.items(), key=lambda pair: -pair[1]))
		return ToolResult(" ".join([*notes, f"{title}{josa(title, '은', '는')} {len(people)}명이에요. 사유: {detail}. "
			"편성인원목록에 필터를 걸었어요."]), _roster(title, ids), conditions=chips)

	if condition.training == "shortfall":
		title = f"{label} 교육 미달자".strip()
		if not people:
			return ToolResult(" ".join([*notes, f"{title}{josa(title, '이', '가')} 없어요. "
				"올해 교육 대상은 모두 필요 시간을 채웠어요."]), conditions=chips)
		hours = [resolved.hours[number] for number in ids]
		return ToolResult(" ".join([*notes,
			f"{title}{josa(title, '은', '는')} {len(people)}명이에요. 남은 시간 합계 {sum(item.remaining for item in hours)}시간, "
			f"올해 한 시간도 못 채운 인원 {sum(item.completed == 0 for item in hours)}명, "
			f"지난 연차 미이수가 이월된 인원 {sum(item.carryover > 0 for item in hours)}명. "
			"남은 시간이 많은 순으로 편성인원목록에 필터를 걸었어요."]), _roster(title, ids), conditions=chips)

	label = label or "전체 인원"
	if not people:
		return ToolResult(" ".join([*notes, f"{label} 조건에 맞는 인원이 없어요."]), conditions=chips)
	return ToolResult(
		" ".join([*notes, f"{label}{josa(label, '은', '는')} {len(people)}명이에요. 편성인원목록에 이 조건으로 필터를 걸었어요."]),
		_roster(label, ids),
		conditions=chips,
	)


# ---------------------------------------------------- recommend_squad_for_transfer

# 분대 추천 (자동편성)
class TransferSquadArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	military_number: str | None = Field(default=None, max_length=50, description="군번")
	name: str | None = Field(default=None, max_length=20, description="이름. 군번도 이름도 없으면 가장 최근 전입자")


def _options(db: Session, recommendations: list[dict[str, object]]) -> list[SquadOption]:
	return [
		SquadOption(
			squad_id=int(item["squad_id"]),
			squad_name=squad_label(db, int(item["squad_id"])),
			current_count=int(item["current_count"]),
			reason=str(item["reason"]),
		)
		for item in recommendations
	]


def _who(person: Person, particle: tuple[str, str] = ("은", "는")) -> str:
	return (f"{person.name}({person.military_number}, {person.branch} {person.rank or '계급 미등록'}, "
		f"{person.position or '직책 미지정'}){josa(person.name, *particle)}")


def _preview_pending(db: Session, transfer: TransferIntake, pending_total: int) -> ToolResult:
	# 확인 전이라 DB에 Person이 없다. 세션에 넣지 않은 임시 객체로 추천만 계산한다.
	person = Person(**{**transfer.person_details, "squad_id": None})
	options = _options(db, recommend_squads_for(db, person))
	actions = [
		UiAction(type="navigate", tab="roster", subtab="transfers"),
		UiAction(type="highlight", tab="roster", subtab="transfers", ids=[transfer.military_number]),
	]
	waiting = f" 확인 대기 중인 전입자는 모두 {pending_total}명이에요." if pending_total > 1 else ""
	if not options:
		return ToolResult(
			f"{_who(person)} 전입 확인 대기 중인데, 호환되는 분대가 없어서 지금 확인하면 실패해요. "
			f"편제에 분대를 먼저 추가해 주세요.{waiting}",
			actions,
		)
	others = ", ".join(f"{option.squad_name}(현재 {option.current_count}명)" for option in options[1:])
	return ToolResult(
		f"{_who(person)} 전입 확인 대기 중이에요. 전입자 화면에서 [확인]하면 1순위인 "
		f"{options[0].squad_name}(현재 {options[0].current_count}명)에 자동 배정됩니다."
		+ (f" 다른 후보: {others}." if others else "") + waiting,
		actions,
	)


def _propose_for_person(db: Session, person: Person) -> ToolResult:
	if person.squad_id is not None:
		# 이미 편성된 사람에게 "편성해줘" = 다른 분대로 옮기기. 막다른 답 대신 재편성 카드를 보여준다.
		return propose_move(db, MoveArgs(military_number=person.military_number))
	if not is_assignable(person):
		return ToolResult(f"{_who(person)} 편성 대상이 아니에요 ({not_assignable_reason(person)}).")
	options = _options(db, recommend_squads_for(db, person))
	if not options:
		return ToolResult(f"{_who(person)} 편성할 수 있는 {person.branch} {personnel_category(person.rank)} 분대가 없어요 "
			"(같은 군별·구분이면서 빈자리가 있는 분대가 없음). 편제 화면에서 분대를 추가한 뒤 다시 요청해 주세요.")
	return ToolResult(
		f"{_who(person, ('의', '의'))} 추천 분대 {len(options)}곳이에요. 카드에서 분대를 고르고 [승인]을 누르면 편성됩니다.",
		proposal=Proposal(
			kind="assign_squad",
			title=f"{person.name} 분대 편성",
			person_id=person.military_number,
			options=options,
		),
	)


def recommend_squad_for_transfer(db: Session, args: TransferSquadArgs) -> ToolResult:
	pending = list(db.scalars(
		select(TransferIntake).where(TransferIntake.status == "pending")
		.order_by(TransferIntake.submitted_at.desc(), TransferIntake.id.desc())
	).all())

	if args.name and not args.military_number:
		name = args.name.strip()
		# "황성민은"처럼 조사가 붙어 왔으면 떼고 한 번 더 찾는다.
		for candidate in (name, name[:-1] if len(name) > 2 and name[-1] in "은는이가을를의님씨" else None):
			if not candidate:
				continue
			transfers = [item for item in pending if item.person_details.get("name") == candidate]
			people = list(db.scalars(select(Person).where(Person.name == candidate).order_by(Person.military_number)).all())
			if transfers or people:
				name = candidate
				break
		if len(transfers) + len(people) == 0:
			return ToolResult(f"'{name}'{josa(name, '이라는', '라는')} 인원이나 전입 신청을 찾지 못했어요.")
		if len(transfers) + len(people) > 1:
			numbers = [item.military_number for item in transfers] + [person.military_number for person in people]
			return ToolResult(
				f"'{name}'{josa(name, '이', '가')} {len(numbers)}명이에요. 군번으로 알려 주세요: {', '.join(numbers)}",
				[UiAction(type="navigate", tab="roster", subtab="people"),
				 UiAction(type="filter", tab="roster", label=f"'{name}'", ids=numbers)],
			)
		return _preview_pending(db, transfers[0], len(pending)) if transfers else _propose_for_person(db, people[0])

	if args.military_number:
		number = args.military_number.strip()
		transfer = next((item for item in pending if item.military_number == number), None)
		if transfer is not None:
			return _preview_pending(db, transfer, len(pending))
		person = db.get(Person, number)
		if person is None:
			return ToolResult(f"군번 {number}인 인원이나 전입 신청을 찾지 못했어요.")
		return _propose_for_person(db, person)

	if pending:
		return _preview_pending(db, pending[0], len(pending))

	unassigned = search_people(db, PersonSearch(registration_type=TRANSFER_REGISTRATION, assigned=False))
	if len(unassigned) == 1:
		return _propose_for_person(db, unassigned[0])
	if not unassigned:
		return ToolResult("확인 대기 중인 전입 신청도, 미편성 전입자도 없어요.")
	examples = ", ".join(person.military_number for person in unassigned[:3])
	return ToolResult(
		f"확인 대기 중인 전입 신청은 없고, 미편성 전입자가 {len(unassigned)}명이에요. "
		f"어느 분인지 군번으로 알려 주세요. 예: \"{unassigned[0].military_number} 어디 편성해?\" ({examples} …)",
		[UiAction(type="navigate", tab="roster", subtab="people"),
		 UiAction(type="filter", tab="roster", label="미편성 전입자", ids=[person.military_number for person in unassigned])],
	)


# ------------------------------------------------------------------- propose_move

class MoveArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	military_number: str | None = Field(default=None, max_length=50, description="군번")
	name: str | None = Field(default=None, max_length=20, description="이름")
	avoid_platoon: str | None = Field(default=None, pattern=r"^\d{1,2}소대$",
		description="옮기면 안 되는 소대. 예: '1소대에 있으면 안 돼' → 1소대")
	other_platoon: bool = Field(default=False, description="지금 소대가 아닌 다른 소대로 옮길 때 true")


def _find_one(db: Session, military_number: str | None, name: str | None) -> Person | ToolResult:
	if military_number:
		person = db.get(Person, military_number.strip())
		return person or ToolResult(f"군번 {military_number}인 인원을 찾지 못했어요.")
	if not name:
		return ToolResult("누구를 재편성할지 이름이나 군번을 알려 주세요. 예: \"정태윤 재편성해줘\"")
	name = name.strip()
	# "정태윤은"처럼 조사가 붙어 왔으면 떼고 한 번 더 찾는다.
	for candidate in (name, name[:-1] if len(name) > 2 and name[-1] in "은는이가을를의님씨" else None):
		if not candidate:
			continue
		people = list(db.scalars(select(Person).where(Person.name == candidate).order_by(Person.military_number)).all())
		if len(people) == 1:
			return people[0]
		if people:
			numbers = [person.military_number for person in people]
			return ToolResult(
				f"'{candidate}'{josa(candidate, '이', '가')} {len(numbers)}명이에요. 군번으로 알려 주세요: {', '.join(numbers)}",
				[UiAction(type="navigate", tab="roster", subtab="people"),
				 UiAction(type="filter", tab="roster", label=f"'{candidate}'", ids=numbers)],
			)
	return ToolResult(f"'{name}'{josa(name, '이라는', '라는')} 인원을 찾지 못했어요.")


def propose_move(db: Session, args: MoveArgs) -> ToolResult:
	found = _find_one(db, args.military_number, args.name)
	if isinstance(found, ToolResult):
		return found
	person = found
	if person.squad_id is None:
		# 아직 편성 전이면 재편성이 아니라 일반 편성 추천이다.
		return _propose_for_person(db, person)
	if not is_assignable(person):
		return ToolResult(f"{_who(person)} 편성 대상이 아니에요 ({not_assignable_reason(person)}). "
			f"옮기지 말고 해제하려면 \"{person.name} 편성 해제해줘\"라고 해 주세요.")

	current = squad_label(db, person.squad_id)
	node = db.scalar(select(OrganizationNode).where(OrganizationNode.squad_id == person.squad_id))
	parent = db.get(OrganizationNode, node.parent_id) if node is not None and node.parent_id else None
	current_platoon = parent.name if parent is not None and parent.kind == "platoon" else None
	avoid = {args.avoid_platoon} if args.avoid_platoon else set()
	if args.other_platoon and current_platoon:
		avoid.add(current_platoon)
	excluded = {person.squad_id}
	for platoon in avoid:
		excluded.update(squad_ids_for_platoon(db, platoon))

	options = _options(db, recommend_squads_for(db, person, exclude_squad_ids=excluded))
	who = f"{_who(person)} 지금 {current}에 있어요."
	where = f"{', '.join(sorted(avoid))}를 뺀 " if avoid else ""
	if not options:
		return ToolResult(f"{who} {where}옮길 수 있는 {person.branch} {personnel_category(person.rank)} 분대가 없어요 "
			"(같은 군별·구분이면서 빈자리가 있는 분대가 없음). 편제 화면에서 분대를 추가한 뒤 다시 요청해 주세요.")
	return ToolResult(
		f"{who} {where}옮길 수 있는 분대 {len(options)}곳이에요. 카드에서 분대를 고르고 [승인]하면 옮겨집니다.",
		[UiAction(type="navigate", tab="roster", subtab="people"),
		 UiAction(type="highlight", tab="roster", subtab="people", ids=[person.military_number])],
		Proposal(
			kind="move",
			title=f"{person.name} 재편성 ({current} → ?)",
			person_id=person.military_number,
			options=options,
			notes=[f"현재 {current}에서 빠지고 고른 분대로 옮겨집니다. 같은 군별·구분이면서 빈자리가 있는 분대만 보여요."],
		),
	)


# ------------------------------------------------------- propose_bulk_assignment

class BulkAssignmentArgs(PersonFilter):
	"""대상은 항상 미편성 인원이다(assigned 조건은 무시)."""

	# 직전 답변의 명단("저 인원들"). LLM에는 보이지 않고 라우터가 채운다.
	military_numbers: SkipJsonSchema[list[str] | None] = None
	scope_label: SkipJsonSchema[str | None] = None


SQUAD_SIZE = 11


def _plan_bulk(db: Session, people: list[Person]) -> tuple[list[dict[str, object]], dict[str, int], dict[str, int]] | None:
	"""(편성안, 제외 사유별 인원, 빈자리 없는 군별·구분별 인원). 편제가 없으면 None."""
	# 편제 화면의 [자동 편성]과 같은 규칙(직책·특기 우선순위, 군별·간부/병사 분리, 정원)으로 계획만 세운다.
	root_id = root_node_id(db)
	if root_id is None:
		return None
	planned = [
		{"military_number": person.military_number, "name": person.name, "squad_id": squad_id}
		for person, squad_id in plan_vacancies(db, root_id, people)["planned"]
	]
	placed = {item["military_number"] for item in planned}
	reasons: dict[str, int] = {}
	no_room: dict[str, int] = {}
	for person in people:
		if person.military_number in placed:
			continue
		if not is_assignable(person):
			reason = f"편성 대상 아님 ({not_assignable_reason(person)})"
		else:
			group = f"{person.branch} {personnel_category(person.rank)}"
			no_room[group] = no_room.get(group, 0) + 1
			reason = f"{group} 분대에 빈자리 없음"
		reasons[reason] = reasons.get(reason, 0) + 1
	return planned, reasons, no_room


def squads_needed(no_room: dict[str, int]) -> int:
	"""한 분대에 군별·간부/병사를 섞지 않으므로 그룹마다 따로 올림한다."""
	return sum(-(-count // SQUAD_SIZE) for count in no_room.values())


def no_room_note(no_room: dict[str, int]) -> str:
	"""빈자리 부족 안내. Copilot은 분대를 만들지 않는다(편제 화면에서 사람이 직접 추가)."""
	detail = ", ".join(f"{group} {people}명" for group, people in sorted(no_room.items(), key=lambda pair: -pair[1]))
	return (f"빈자리가 없는 {sum(no_room.values())}명({detail})은 분대가 약 {squads_needed(no_room)}개 더 있어야 편성할 수 있어요. "
		"편제 화면에서 분대를 직접 추가한 뒤 다시 요청해 주세요.")


def propose_bulk_assignment(db: Session, args: BulkAssignmentArgs) -> ToolResult:
	already_assigned = 0
	if args.military_numbers is not None:
		chosen = set(args.military_numbers)
		in_scope = [person for person in db.scalars(select(Person).where(Person.military_number.in_(chosen))).all()]
		if not args.is_empty():
			allowed = {person.military_number for person in resolve_people(db, args.conditions()).people}
			in_scope = [person for person in in_scope if person.military_number in allowed]
		people = sorted((person for person in in_scope if person.squad_id is None), key=lambda person: person.military_number)
		already_assigned = len(in_scope) - len(people)
		chips = [args.scope_label or "선택한 인원", *args.conditions().labels()]
		label = " ".join(chips)
	else:
		resolved = resolve_people(db, args.conditions().model_copy(update={"assigned": False}))
		chips = (resolved.applied or args).labels()
		if resolved.question:
			return ToolResult(resolved.question, conditions=chips)
		people = resolved.people
		parts = (resolved.applied or args).model_copy(update={"assigned": None}).labels()
		label = f"미편성 {' '.join(parts)}" if parts else "미편성 인원"
	if not people:
		if already_assigned:
			return ToolResult(f"{label} {already_assigned}명은 모두 이미 편성돼 있어요.", conditions=chips)
		return ToolResult(f"{label}{josa(label, '이', '가')} 없어요.", conditions=chips)

	result = _plan_bulk(db, people)
	if result is None:
		return ToolResult("편제가 없어요. 편제 화면에서 소대와 분대를 먼저 만들어 주세요.")
	planned, reasons, no_room = result
	names = {squad_id: squad_label(db, squad_id) for squad_id in {int(item["squad_id"]) for item in planned}}
	notes = [f"제외 {count}명: {reason}" for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1])]
	if planned and no_room:
		notes.append(no_room_note(no_room))

	filter_action = [UiAction(type="navigate", tab="roster", subtab="people"),
		UiAction(type="filter", tab="roster", label=label, ids=[person.military_number for person in people])]
	if not planned:
		lead = f"{label} {len(people)}명 중 지금 편성할 수 있는 인원이 없어요."
		if no_room:
			return ToolResult(f"{lead} {no_room_note(no_room)}", filter_action, conditions=chips)
		return ToolResult(lead + " " + " / ".join(notes), filter_action, conditions=chips)
	summary = f"{label} {len(people)}명 중 {len(planned)}명을 분대 {len(names)}곳에 배치하는 안을 만들었어요."
	excluded = len(people) - len(planned)
	if excluded:
		summary += f" {excluded}명은 제외했어요."
	if already_assigned:
		summary += f" (이미 편성된 {already_assigned}명은 빼고 계산했어요.)"
	return ToolResult(
		summary + " 카드에서 확인하고 [승인]하면 저장됩니다.",
		filter_action,
		Proposal(
			kind="assign_bulk",
			title=f"{label} 일괄 편성 ({len(planned)}명)",
			assignments=[
				PlannedAssignment(
					person_id=str(item["military_number"]),
					name=str(item["name"]),
					squad_id=int(item["squad_id"]),
					squad_name=names[int(item["squad_id"])],
				)
				for item in planned
			],
			notes=notes,
		),
		conditions=chips,
	)


# ------------------------------------------------------------ explain_squad_shortage

class SquadShortageArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")


def explain_squad_shortage(db: Session, args: SquadShortageArgs) -> ToolResult:
	"""분대를 추가해 달라는 요청. 만들지는 않고, 몇 개가 모자라는지만 알려 준다."""
	result = _plan_bulk(db, search_people(db, PersonSearch(assigned=False)))
	if result is None:
		return ToolResult("편제가 없어요. 편제 화면에서 소대와 분대를 먼저 만들어 주세요.")
	planned, _, no_room = result
	lead = "Copilot은 분대를 추가하지 않아요."
	if not no_room:
		return ToolResult(f"{lead} 지금은 미편성 편성 대상이 모두 기존 분대의 빈자리에 들어갈 수 있어서 분대를 더 만들 필요가 없어요."
			+ (" \"미편성 인원들 편성해줘\"라고 하시면 편성안을 만들어 드려요." if planned else ""))
	return ToolResult(f"{lead} {no_room_note(no_room)}")


# ------------------------------------------------------------------ propose_release

class ReleaseArgs(PersonFilter):
	# 직전 답변의 명단("저 인원들"). LLM에는 보이지 않고 라우터가 채운다.
	military_numbers: SkipJsonSchema[list[str] | None] = None
	scope_label: SkipJsonSchema[str | None] = None


def propose_release(db: Session, args: ReleaseArgs) -> ToolResult:
	condition = args.conditions().model_copy(update={"assigned": True})
	if args.military_numbers is not None:
		chosen = set(args.military_numbers)
		people = [person for person in resolve_people(db, condition).people if person.military_number in chosen]
		chips = [args.scope_label or "선택한 인원", *args.conditions().labels()]
		label = " ".join(chips)
	else:
		if args.is_empty():
			return ToolResult("누구의 편성을 해제할지 조건을 말씀해 주세요. 예: \"0년차 편성된 사람 빼줘\", \"1소대 3분대 비워줘\"")
		resolved = resolve_people(db, condition)
		chips = (resolved.applied or condition).labels()
		if resolved.question:
			return ToolResult(resolved.question, conditions=chips)
		people = resolved.people
		label = " ".join((resolved.applied or condition).model_copy(update={"assigned": None}).labels())
	if not people:
		return ToolResult(f"{label} 중 편성된 인원이 없어요.", conditions=chips)
	people.sort(key=lambda person: (person.squad_id, person.military_number))
	names = {squad_id: squad_label(db, squad_id) for squad_id in {person.squad_id for person in people}}
	return ToolResult(
		f"편성된 {label} {len(people)}명({len(names)}개 분대)의 편성을 해제하는 안이에요. 카드에서 확인하고 [승인]하면 해제됩니다.",
		[UiAction(type="navigate", tab="roster", subtab="people"),
		 UiAction(type="filter", tab="roster", label=f"{label} (해제 대상)", ids=[person.military_number for person in people])],
		Proposal(
			kind="release",
			title=f"{label} 편성 해제 ({len(people)}명)",
			assignments=[
				PlannedAssignment(person_id=person.military_number, name=person.name,
					squad_id=int(person.squad_id), squad_name=names[person.squad_id])
				for person in people
			],
			notes=["해제하면 미편성으로 돌아가고, 동원 상태는 동원미지정으로 바뀝니다."],
		),
		conditions=chips,
	)


from user.app.copilot.insights import (  # noqa: E402  조회 도구는 insights.py에 있다.
	DataCheckArgs, PersonSummaryArgs, RecentChangesArgs, StatusArgs,
	check_data_issues, person_summary, show_recent_changes, summarize_status,
)

TOOLS: dict[str, Tool] = {
	tool.name: tool
	for tool in (
		Tool(
			name="search_members",
			description="소대·분대·군별·간부/병사·계급·연차·편성 여부·교육 미달·고발 검토 대상·이름 같은 조건으로 인원 명단을 찾을 때 사용",
			args_model=SearchMembersArgs,
			kind="조회",
			run=search_members,
		),
		Tool(
			name="recommend_squad_for_transfer",
			description="한 사람(이름·군번, 또는 방금 등록한 전입자)을 어느 분대에 편성하면 좋은지 물을 때 사용",
			args_model=TransferSquadArgs,
			kind="제안",
			run=recommend_squad_for_transfer,
		),
		Tool(
			name="propose_move",
			description="이미 편성된 한 사람을 다른 분대로 옮겨 달라(재편성·이동)고 할 때 사용. 예: 정태윤 재편성해줘, 1소대 말고 다른 데로 옮겨줘",
			args_model=MoveArgs,
			kind="제안",
			run=propose_move,
		),
		Tool(
			name="propose_bulk_assignment",
			description="미편성 인원 여러 명을 한꺼번에 분대에 편성(배치)해 달라고 할 때 사용",
			args_model=BulkAssignmentArgs,
			kind="제안",
			run=propose_bulk_assignment,
		),
		Tool(
			name="propose_release",
			description="편성된 인원의 편성을 해제하거나(빼기) 분대를 비워 달라고 할 때 사용. 예: 0년차 편성된 사람 빼줘, 1소대 3분대 비워줘",
			args_model=ReleaseArgs,
			kind="제안",
			run=propose_release,
		),
		Tool(
			name="explain_squad_shortage",
			description="분대를 추가·증편해 달라고 할 때 사용. Copilot은 분대를 만들지 않고 몇 개가 모자라는지만 안내한다",
			args_model=SquadShortageArgs,
			kind="조회",
			run=explain_squad_shortage,
		),
		Tool(
			name="summarize_status",
			description="오늘 현황·브리핑, 또는 보류자·연기자·고발 대상·결재 대기가 몇 명인지 물을 때 사용",
			args_model=StatusArgs,
			kind="조회",
			run=summarize_status,
		),
		Tool(
			name="person_summary",
			description="한 사람(이름 또는 군번)의 편성·연차·교육 이수·보류 이력을 요약해 달라고 할 때 사용",
			args_model=PersonSummaryArgs,
			kind="조회",
			run=person_summary,
		),
		Tool(
			name="check_data_issues",
			description="이상 데이터·잘못된 편성·데이터 점검을 요청할 때 사용",
			args_model=DataCheckArgs,
			kind="조회",
			run=check_data_issues,
		),
		Tool(
			name="show_recent_changes",
			description="최근 변경 기록(누가 언제 편성·해제했는지)을 물을 때 사용",
			args_model=RecentChangesArgs,
			kind="조회",
			run=show_recent_changes,
		),
	)
}
