"""Business rules for organizing reservists into wartime positions."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from user.app.models.person import Person

POSITION_SPECIALTIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
	"행정병": (("3111101",), ("311102",)),
	"병기취급병": (("222101",), ("222102",)),
	"통신병": (("171101",), ("171102", "171104", "171106")),
	"의무병": (("411101",), ("411102", "411103", "411104", "411105", "411106")),
	"운전병": (("241102",), ("241103", "241104", "231101")),
	"보급병": (("231101",), ("231103", "231104", "231105")),
}

SOLDIER_RANKS = {"이병", "일병", "상병", "병장"}
BRANCHES = ("육군", "해군", "공군", "해병대")


@dataclass(frozen=True)
class AssignmentCandidate:
	person: Person
	tier: str
	personnel_category: str


def normalize_specialty(specialty: str | None) -> str:
	return re.sub(r"\D", "", specialty or "")


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
	"""Group personnel so soldier and officer lists can be shown separately."""
	return "병사" if rank in SOLDIER_RANKS else "간부"


def specialty_priority(tier: str) -> int:
	return {"적소": 0, "유사": 1, "기타": 2, "보충": 3}[tier]


def rank_candidates(
	people: Iterable[Person],
	position: str,
	branch: str | None = None,
) -> list[AssignmentCandidate]:
	"""Prioritize 5-6 year reservists, then specialty-match tiers."""
	candidates = [
		AssignmentCandidate(
			person,
			classify_specialty(position, person.specialty),
			personnel_category(person.rank),
		)
		for person in people
		if branch is None or person.branch == branch
	]

	def sort_key(candidate: AssignmentCandidate) -> tuple[int, int, str]:
		year_priority = 0 if candidate.person.service_year in (5, 6) else 1
		return (year_priority, specialty_priority(candidate.tier), candidate.person.military_number)

	return sorted(candidates, key=sort_key)


def grouped_candidates(
	people: Iterable[Person],
	position: str,
	branch: str | None = None,
) -> dict[str, dict[str, list[AssignmentCandidate]]]:
	"""Return candidates grouped by branch and soldier/officer category."""
	groups: dict[str, dict[str, list[AssignmentCandidate]]] = {
		branch_name: {"병사": [], "간부": []} for branch_name in BRANCHES
	}
	for candidate in rank_candidates(people, position, branch):
		if candidate.person.branch in groups:
			groups[candidate.person.branch][candidate.personnel_category].append(candidate)
	return groups
