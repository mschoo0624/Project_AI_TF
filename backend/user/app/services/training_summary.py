"""Current-year training hours for many people at once.

all_training_progress() runs several queries per person and year (about 7 s for
500 people), which is too slow for a chat answer. This module loads education
records and annual statuses once and applies the same rules:
mobilization_status_for_year, target_training_hours and the carryover in
all_training_progress.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.services.training import COMPLETED, target_training_hours, training_progress


@dataclass(frozen=True)
class YearHours:
	service_year: int
	required: int  # 올해 목표 + 지난 연차에서 넘어온 시간
	carryover: int
	completed: int

	@property
	def remaining(self) -> int:
		return max(self.required - self.completed, 0)


def _status_for_year(person: Person, year: int, annual: dict[tuple[str, int], str]) -> str | None:
	annual_status = annual.get((person.military_number, year))
	status = annual_status if annual_status is not None else person.mobilization_status
	if 1 <= year <= 6 and annual_status is None:
		if person.squad_id is not None:
			return "동원지정"
		if status in {None, "해당없음"}:
			return "동원미지정"
	return status


def current_year_hours(db: Session, people: list[Person]) -> dict[str, YearHours]:
	"""Military number → current service year hours. People without a valid year are skipped."""
	ids = [person.military_number for person in people]
	annual = {
		(row.person_id, row.service_year): row.mobilization_status
		for row in db.scalars(select(AnnualStatus).where(AnnualStatus.person_id.in_(ids))).all()
	}
	completed: dict[tuple[str, int], int] = defaultdict(int)
	for person_id, year, hours in db.execute(
		select(Education.person_id, Education.education_year, Education.training_hours)
		.where(Education.person_id.in_(ids), Education.attendance_status.in_(COMPLETED))
	).all():
		completed[(person_id, year)] += hours or 0

	result: dict[str, YearHours] = {}
	for person in people:
		current = person.service_year
		if current is None or not 0 <= current <= 8:
			continue
		carryover = 0
		for year in range(current + 1):
			year_carryover = carryover if 1 <= year <= 8 else 0
			target = target_training_hours(year, _status_for_year(person, year, annual), person.branch, person.rank)
			hours = YearHours(year, target + year_carryover, year_carryover, completed[(person.military_number, year)])
			carryover = hours.remaining if year < 8 else 0
		result[person.military_number] = hours
	return result


def prosecution_reasons(db: Session, people: list[Person], hours: dict[str, YearHours]) -> dict[str, str]:
	"""Military number → 고발 검토 사유. 판단은 training_progress 그대로 하되,
	미이수·불참 기록이 있는 3년차 이상만 계산한다(그 외에는 대상이 될 수 없다)."""
	ids = [person.military_number for person in people if (person.service_year or 0) >= 3]
	with_failures = set(db.scalars(
		select(Education.person_id).where(Education.person_id.in_(ids), Education.attendance_status.not_in(COMPLETED))
	).all())
	result: dict[str, str] = {}
	for person in people:
		if person.military_number not in with_failures or person.military_number not in hours:
			continue
		progress = training_progress(db, person, person.service_year, hours[person.military_number].carryover)
		if progress["prosecution_risk"]:
			result[person.military_number] = str(progress["prosecution_reason"])
	return result
