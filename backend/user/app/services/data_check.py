"""Data consistency checks: rules the system assumes but stored data may break."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.services.assignment import is_assignable, not_assignable_reason, personnel_category
from user.app.services.training import DESIGNATED

DEFAULT_SQUAD_SIZE = 11


@dataclass
class DataIssue:
	key: str
	title: str
	ids: list[str]
	details: list[str] = field(default_factory=list)
	fix: str | None = None  # Copilot에 이어서 보낼 수 있는 요청


def find_data_issues(db: Session) -> list[DataIssue]:
	people = list(db.scalars(select(Person).order_by(Person.military_number)).all())
	members: dict[int, list[Person]] = defaultdict(list)
	for person in people:
		if person.squad_id is not None:
			members[person.squad_id].append(person)
	nodes = {node.id: node for node in db.scalars(select(OrganizationNode)).all()}
	capacity: dict[int, int] = {}
	names: dict[int, str] = {}
	for node in nodes.values():
		if node.squad_id is None:
			continue
		capacity[node.squad_id] = node.planned_strength or DEFAULT_SQUAD_SIZE
		parent = nodes.get(node.parent_id) if node.parent_id else None
		names[node.squad_id] = f"{parent.name} {node.name}" if parent is not None and parent.kind == "platoon" else node.name
	issues: list[DataIssue] = []

	wrong = [person for person in people if person.squad_id is not None and not is_assignable(person)]
	if wrong:
		reasons: dict[str, int] = defaultdict(int)
		for person in wrong:
			reasons[not_assignable_reason(person)] += 1
		issues.append(DataIssue(
			"assigned_not_assignable", "편성 대상이 아닌데 편성됨", [person.military_number for person in wrong],
			[f"{reason} {count}명" for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1])],
			"편성 대상 아닌 사람 편성 해제해줘",
		))

	mixed = {squad_id: group for squad_id, group in members.items()
		if len({(person.branch, personnel_category(person.rank)) for person in group}) > 1}
	if mixed:
		issues.append(DataIssue(
			"mixed_squad", "군별·간부/병사가 섞인 분대",
			[person.military_number for group in mixed.values() for person in group],
			[f"{names.get(squad_id, f'{squad_id}번 분대')}: " + ", ".join(sorted({f'{p.branch} {personnel_category(p.rank)}' for p in group}))
				for squad_id, group in mixed.items()],
		))

	over = {squad_id: group for squad_id, group in members.items()
		if len(group) > capacity.get(squad_id, DEFAULT_SQUAD_SIZE)}
	if over:
		issues.append(DataIssue(
			"over_capacity", "정원을 넘은 분대",
			[person.military_number for group in over.values() for person in group],
			[f"{names.get(squad_id, f'{squad_id}번 분대')}: {len(group)}명 / 정원 {capacity.get(squad_id, DEFAULT_SQUAD_SIZE)}명"
				for squad_id, group in over.items()],
		))

	no_year = [person for person in people if person.service_year is None]
	if no_year:
		issues.append(DataIssue("missing_service_year", "연차 미등록", [person.military_number for person in no_year]))

	no_status = [person for person in people if person.service_year is not None and 1 <= person.service_year <= 4
		and person.mobilization_status in (None, "", "해당없음")]
	if no_status:
		issues.append(DataIssue(
			"missing_mobilization", "1~4년차인데 동원 상태 없음", [person.military_number for person in no_status],
			["1~4년차는 동원지정/동원미지정/학생예비군/보류 중 하나여야 합니다."],
		))

	# 편성되면 동원지정, 해제되면 동원미지정으로 맞춘다(set_assignment_mobilization_status).
	mismatch = [person for person in people
		if (person.squad_id is not None) != (person.mobilization_status in DESIGNATED)
		and person.mobilization_status in DESIGNATED | {"동원미지정", "미지정"}]
	if mismatch:
		assigned = sum(person.squad_id is not None for person in mismatch)
		issues.append(DataIssue(
			"mobilization_mismatch", "편성 여부와 동원 상태가 다름", [person.military_number for person in mismatch],
			[f"편성됐는데 동원지정이 아님 {assigned}명", f"미편성인데 동원지정 {len(mismatch) - assigned}명"],
		))
	return issues
