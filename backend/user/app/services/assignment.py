"""Business rules for organizing reservists into wartime positions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.assignment import Assignment
from user.app.models.person import Person
from user.app.models.squad import Squad

POSITION_SPECIALTIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
	"행정병": (("3111101",), ("311102",)),
	"병기취급병": (("222101",), ("222102",)),
	"통신병": (("171101",), ("171102", "171104", "171106")),
	"의무병": (("411101",), ("411102", "411103", "411104", "411105", "411106")),
	"운전병": (("241102",), ("241103", "241104", "231101")),
	"보급병": (("231101",), ("231103", "231104", "231105")),
}

SPECIALTY_TO_POSITION: dict[str, str] = {
	"행정": "행정병",
	"행정병": "행정병",
	"3111101": "행정병",
	"311102": "행정병",
	"병기": "병기취급병",
	"병기취급": "병기취급병",
	"병기취급병": "병기취급병",
	"222101": "병기취급병",
	"222102": "병기취급병",
	"통신": "통신병",
	"통신병": "통신병",
	"171101": "통신병",
	"171102": "통신병",
	"171104": "통신병",
	"171106": "통신병",
	"의무": "의무병",
	"의무병": "의무병",
	"411101": "의무병",
	"411102": "의무병",
	"411103": "의무병",
	"411104": "의무병",
	"411105": "의무병",
	"411106": "의무병",
	"운전": "운전병",
	"운전병": "운전병",
	"241102": "운전병",
	"241103": "운전병",
	"241104": "운전병",
	"231101": "운전병",
	"보급": "보급병",
	"보급병": "보급병",
	"231101": "보급병",
	"231103": "보급병",
	"231104": "보급병",
	"231105": "보급병",
}

SOLDIER_RANKS = {"이병", "일병", "상병", "병장"}
NCO_RANKS = {"하사", "중사", "상사", "원사"}
OFFICER_RANKS = {"소위", "중위", "대위", "소령", "중령", "대령"}
BRANCHES = ("육군", "해군", "공군", "해병대")
PERSONNEL_CATEGORIES = ("병사", "부사관", "장교")


@dataclass(frozen=True)
class AssignmentCandidate:
	person: Person
	tier: str
	personnel_category: str

def normalize_specialty(specialty: str | None) -> str:
	return re.sub(r"\D", "", specialty or "")

def suggest_position_for_specialty(specialty: str | None) -> str | None:
	if specialty is None:
		return None

	candidate = specialty.strip()

	if not candidate:
		return None
	for value in (candidate, candidate.replace(" ", ""), re.sub(r"\D", "", candidate)):
		if not value:
			continue
		compact = re.sub(r"[^가-힣a-zA-Z0-9]", "", value).lower()
		match = SPECIALTY_TO_POSITION.get(compact)
		if match:
			return match
		match = SPECIALTY_TO_POSITION.get(value)
		if match:
			return match
	match = SPECIALTY_TO_POSITION.get(candidate.lower())
	if match:
		return match
	return None


def classify_specialty(position: str, specialty: str | None) -> str:
	"""Classify a specialty as 적소, 유사, 기타, or 보충."""
	code = normalize_specialty(specialty)
	primary, alternate = POSITION_SPECIALTIES.get(position, ((), ()))
	if code in primary:
		return "적소"
	if code in alternate:
		return "유사"
	if position == "의무병" and code.startswith(("4112", "4113", "4114", "4115")):
		return "유사"
	return "기타" if code else "보충"


def personnel_category(rank: str | None) -> str:
	"""Group personnel into the three formation categories."""
	if rank in SOLDIER_RANKS:
		return "병사"
	if rank in NCO_RANKS:
		return "부사관"
	if rank in OFFICER_RANKS:
		return "장교"
	return "기타"


def specialty_priority(tier: str) -> int:
	return {"적소": 0, "유사": 1, "기타": 2, "보충": 3}[tier]


def rank_candidates(
	people: Iterable[Person],
	position: str,
	branch: str | None = None,
) -> list[AssignmentCandidate]:
	"""Prioritize eligible soldiers and then specialty-match tiers."""
	candidates = [
		AssignmentCandidate(
			person,
			classify_specialty(position, person.specialty),
			personnel_category(person.rank),
		)
		for person in people
		if branch is None or person.branch == branch
	]

	def sort_key(candidate: AssignmentCandidate) -> tuple[int, int, int, int, str]:
		year_priority = 0 if candidate.personnel_category == "병사" and candidate.person.service_year in (5, 6) else 1
		service_year = candidate.person.service_year if candidate.person.service_year is not None else 99
		return (
			year_priority,
			specialty_priority(candidate.tier),
		0 if candidate.personnel_category == "병사" else 1,
		service_year,
			candidate.person.military_number,
		)

	return sorted(candidates, key=sort_key)


def is_priority_medic_origin(person: Person) -> bool:
	"""Return whether verified data marks a person as a priority medic origin."""
	return person.origin_type in {"공중보건의", "공중보건의출신", "public_health_doctor"}


def rank_candidates_for_position(
	people: Iterable[Person], position: str
) -> list[AssignmentCandidate]:
	"""Rank one position with the medic origin exception applied."""
	ranked = rank_candidates(people, position)
	if position != "의무병":
		return ranked
	return sorted(ranked, key=lambda candidate: (
		0 if candidate.personnel_category == "병사" and candidate.person.service_year in (5, 6) else 1,
		0 if candidate.personnel_category == "병사" and candidate.person.service_year in (5, 6) and is_priority_medic_origin(candidate.person) else 1,
		specialty_priority(candidate.tier),
		candidate.person.service_year if candidate.person.service_year is not None else 99,
		candidate.person.military_number,
	))


def fill_squad_positions(
	db: Session,
	squad_id: int,
	position_quotas: dict[str, int] | dict[str, dict[str, int]],
	branch_order: tuple[str, ...] = BRANCHES,
	allow_branch_merge: bool = True,
) -> dict[str, object]:
	"""Fill one squad from the shared, unassigned candidate pool."""
	for quota in position_quotas.values():
		values = (quota,) if isinstance(quota, int) else quota.values()
		if any(value < 0 for value in values):
			raise ValueError("Position quotas must be non-negative")
	if db.get(Squad, squad_id) is None:
		raise ValueError(f"Squad {squad_id} not found")

	try:
		remaining = list(
			db.scalars(
				select(Person).where(
					Person.status == "active",
					Person.squad_id.is_(None),
				)
			).all()
		)
		positions: dict[str, object] = {}
		assigned_total = 0
		squad_group = {
			(member.branch, personnel_category(member.rank))
			for member in db.scalars(select(Person).where(Person.squad_id == squad_id)).all()
		}
		for position, quota_spec in position_quotas.items():
			quotas_by_category = {"전체": quota_spec} if isinstance(quota_spec, int) else quota_spec
			selected: list[AssignmentCandidate] = []
			for category, quota in quotas_by_category.items():
				candidates = [
					person for person in remaining
					if person.position == position
					and (category == "전체" or personnel_category(person.rank) == category)
				]
				ranked = rank_candidates_for_position(candidates, position)
				if branch_order:
					ranked = sorted(
						ranked,
						key=lambda candidate: (
							branch_order.index(candidate.person.branch)
							if candidate.person.branch in branch_order else len(branch_order),
						),
					)
				selected.extend(ranked[:quota])
			if not allow_branch_merge:
				selected = [candidate for candidate in selected if candidate.person.branch == branch_order[0]]
			assigned = []
			for candidate in selected:
				person = candidate.person
				person_group = (person.branch, personnel_category(person.rank))
				if squad_group and squad_group != {person_group}:
					raise ValueError("A squad cannot mix branches or personnel categories")
				squad_group.add(person_group)
				person.squad_id = squad_id
				db.add(
					Assignment(
						person_id=person.military_number,
						squad_id=squad_id,
						assigned_date=date.today(),
						status="assigned",
					)
				)
				remaining.remove(person)
				assigned.append({"military_number": person.military_number, "name": person.name})
			assigned_total += len(assigned)
			requested = sum(quotas_by_category.values())
			positions[position] = {
				"requested": requested,
				"assigned": assigned,
				"shortfall": requested - len(assigned),
			}
		db.commit()
		return {
			"squad_id": squad_id,
			"positions": positions,
			"total_requested": sum(
				quota if isinstance(quota, int) else sum(quota.values())
				for quota in position_quotas.values()
			),
			"total_assigned": assigned_total,
			"total_shortfall": sum(item["shortfall"] for item in positions.values()),
		}
	except Exception:
		db.rollback()
		raise


def available_assignment_candidates(
	db: Session,
	position: str | None = None,
) -> dict[str, dict[str, list[dict[str, object]]]]:
	"""Return currently eligible, unassigned candidates grouped for the UI."""
	people = list(
		db.scalars(
			select(Person).where(
				Person.status == "active",
				Person.squad_id.is_(None),
			)
		).all()
	)
	result = {branch: {category: [] for category in PERSONNEL_CATEGORIES} for branch in BRANCHES}
	positions = {position} if position else {person.position for person in people if person.position}
	for current_position in positions:
		for candidate in rank_candidates_for_position(
			[person for person in people if person.position == current_position],
			current_position,
		):
			if candidate.person.branch in result and candidate.personnel_category in result[candidate.person.branch]:
				result[candidate.person.branch][candidate.personnel_category].append({
					"military_number": candidate.person.military_number,
					"name": candidate.person.name,
					"position": current_position,
					"specialty": candidate.person.specialty,
					"service_year": candidate.person.service_year,
					"origin_type": candidate.person.origin_type,
					"personnel_category": candidate.personnel_category,
					"tier": candidate.tier,
				})
	return result


def confirm_assignment_selections(
	db: Session,
	selections: Iterable[tuple[str, int]],
) -> dict[str, object]:
	"""Persist a reviewed assignment proposal as one atomic operation."""
	selection_list = list(selections)
	if len({person_id for person_id, _ in selection_list}) != len(selection_list):
		raise ValueError("The same person cannot be selected more than once")

	try:
		assigned = []
		selected_groups: dict[int, tuple[str | None, str]] = {}
		for person_id, squad_id in selection_list:
			if db.get(Squad, squad_id) is None:
				raise ValueError(f"Squad {squad_id} not found")
			person = db.get(Person, person_id)
			if person is None:
				raise ValueError(f"Person {person_id} not found")
			if person.service_year is None or person.status != "active":
				raise ValueError(f"Person {person_id} is not eligible for assignment")
			if person.squad_id is not None:
				raise ValueError(f"Person {person_id} is already assigned")
			person_group = (person.branch, personnel_category(person.rank))
			known_group = selected_groups.get(squad_id)
			if known_group is not None and known_group != person_group:
				raise ValueError("A squad cannot mix branches or personnel categories")
			existing_groups = {
				(member.branch, personnel_category(member.rank))
				for member in db.scalars(select(Person).where(Person.squad_id == squad_id)).all()
			}
			if existing_groups and existing_groups != {person_group}:
				raise ValueError("A squad cannot mix branches or personnel categories")
			selected_groups[squad_id] = person_group
			person.squad_id = squad_id
			db.add(
				Assignment(
					person_id=person_id,
					squad_id=squad_id,
					assigned_date=date.today(),
					status="assigned",
				)
			)
			assigned.append({"military_number": person_id, "name": person.name, "squad_id": squad_id})
		db.commit()
		return {"total_assigned": len(assigned), "assigned": assigned}
	except Exception:
		db.rollback()
		raise


def reset_assignment_pool(db: Session) -> dict[str, int]:
	"""Move every reservist back to the temporary, unassigned pool."""
	try:
		reset_count = db.query(Person).filter(Person.squad_id.is_not(None)).update(
			{Person.squad_id: None}, synchronize_session=False
		)
		db.query(Assignment).delete(synchronize_session=False)
		db.commit()
		return {"reset_count": reset_count}
	except Exception:
		db.rollback()
		raise


def auto_assign_people(
	db: Session,
	limit: int | None = None,
) -> dict[str, object]:
	"""Reset assignments and distribute people by branch and personnel category."""
	if limit is not None and limit < 1:
		raise ValueError("Assignment limit must be positive")

	try:
		reset_assignment_pool(db)
		people = list(
			db.scalars(
				select(Person).where(Person.status == "active").order_by(Person.military_number)
			).all()
		)
		squads = list(db.scalars(select(Squad).order_by(Squad.id)).all())
		if not squads:
			raise ValueError("No squads are available")

		groups: dict[tuple[str, str], list[Person]] = {}
		for person in people:
			groups.setdefault((person.branch, personnel_category(person.rank)), []).append(person)
		if len(groups) > len(squads):
			raise ValueError("There are not enough squads to keep branches and personnel categories separate")

		position_order = {position: index for index, position in enumerate(POSITION_SPECIALTIES)}
		assigned: list[dict[str, object]] = []
		assigned_count = 0
		for group_index, (group, group_people) in enumerate(sorted(groups.items())):
			squad = squads[group_index]
			ordered: list[AssignmentCandidate] = []
			for position in sorted(
				{person.position for person in group_people},
				key=lambda value: position_order.get(value or "", len(position_order)),
			):
				position_people = [person for person in group_people if person.position == position]
				ordered.extend(rank_candidates_for_position(position_people, position or ""))
			ordered.extend(
				AssignmentCandidate(person, classify_specialty(person.position or "", person.specialty), group[1])
				for person in group_people
				if person.position is None
			)
			for candidate in ordered:
				if limit is not None and assigned_count >= limit:
					break
				person = candidate.person
				person.squad_id = squad.id
				db.add(
					Assignment(
						person_id=person.military_number,
						squad_id=squad.id,
						assigned_date=date.today(),
						status="assigned",
					)
				)
				assigned.append({
					"military_number": person.military_number,
					"name": person.name,
					"squad_id": squad.id,
					"branch": person.branch,
					"category": group[1],
					"position": person.position,
					"specialty": person.specialty,
					"tier": candidate.tier,
				})
				assigned_count += 1
		db.commit()
		return {"total_assigned": len(assigned), "assigned": assigned}
	except Exception:
		db.rollback()
		raise


def recommend_squads_for_person(db: Session, person_id: str) -> list[dict[str, object]]:
	"""Recommend up to three compatible squads for an unassigned transfer-in."""
	person = db.get(Person, person_id)
	if person is None:
		raise ValueError(f"Person {person_id} not found")
	if person.squad_id is not None:
		raise ValueError(f"Person {person_id} is already assigned")
	group = (person.branch, personnel_category(person.rank))
	candidates = []
	for squad in db.scalars(select(Squad).order_by(Squad.id)).all():
		members = list(squad.persons)
		groups = {(member.branch, personnel_category(member.rank)) for member in members}
		if groups and groups != {group}:
			continue
		position_count = sum(member.position == person.position for member in members)
		tier = classify_specialty(person.position or "", person.specialty)
		matching_specialty_count = sum(
			classify_specialty(person.position or "", member.specialty) == tier
			for member in members
			if member.position == person.position
		)
		candidates.append({
			"squad_id": squad.id,
			"squad_name": squad.name,
			"current_count": len(members),
			"same_position_count": position_count,
			"same_tier_count": matching_specialty_count,
			"reason": f"{person.branch} {personnel_category(person.rank)} 호환 · {person.position or '직책 미지정'} 균형",
			"score": (len(members), position_count, matching_specialty_count, squad.id),
		})
	return sorted(candidates, key=lambda item: item["score"])[:3]


def grouped_candidates(
	people: Iterable[Person],
	position: str,
	branch: str | None = None,
) -> dict[str, dict[str, list[AssignmentCandidate]]]:
	"""Return candidates grouped by branch and soldier/officer category."""
	groups: dict[str, dict[str, list[AssignmentCandidate]]] = {
		branch_name: {category: [] for category in PERSONNEL_CATEGORIES}
		for branch_name in BRANCHES
	}
	for candidate in rank_candidates(people, position, branch):
		if candidate.person.branch in groups:
			groups[candidate.person.branch][candidate.personnel_category].append(candidate)
	return groups
