"""Business rules for organizing reservists into wartime positions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from user.app.models.person import Person

POSITION_SPECIALTIES: dict[str, tuple[str, ...]] = {
	"행정병": ("3111101", "3111102"),
	"병기취급병": ("222101", "222102"),
	"통신병": ("171101", "171102", "171104", "171106"),
	"의무병": ("411101", "411102", "411103", "411104", "411105", "411106"),
	"운전병": ("241102", "241103", "241104", "231101"),
	"보급병": ("231101", "231103", "231104", "231105"),
}


@dataclass(frozen=True)
class AssignmentCandidate:
	person: Person
	tier: str


def normalize_specialty(specialty: str | None) -> str:
	return re.sub(r"\D", "", specialty or "")


def classify_specialty(position: str, specialty: str | None) -> str:
	"""Classify a specialty as 적소, 유사, 기타, or 보충."""
	code = normalize_specialty(specialty)
	if code in POSITION_SPECIALTIES.get(position, ()):
		return "적소"
	if position == "의무병" and code.startswith(("4112", "4113", "4114", "4115")):
		return "유사"
	return "기타" if code else "보충"


def rank_candidates(people: Iterable[Person], position: str) -> list[AssignmentCandidate]:
	"""Prioritize 5-6 year reservists, then specialty-match tiers."""
	candidates = [
		AssignmentCandidate(person, classify_specialty(position, person.specialty))
		for person in people
	]
	tier_order = {"적소": 0, "유사": 1, "기타": 2, "보충": 3}

	def sort_key(candidate: AssignmentCandidate) -> tuple[int, int, str]:
		year_priority = 0 if candidate.person.service_year in (5, 6) else 1
		return (year_priority, tier_order[candidate.tier], candidate.person.military_number)

	return sorted(candidates, key=sort_key)
