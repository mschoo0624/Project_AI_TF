"""Annual reserve-training hour rules and progress calculations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.models.education import Education
from user.app.models.person import Person

DESIGNATED = {"지정", "동원지정", "designated"}
NON_DESIGNATED = {"미지정", "동원미지정", "non_designated"}
STUDENT = {"학생", "학생예비군", "student"}
NAVY_AIR = {"해군", "공군"}
COMPLETED = {"이수", "completed"}
UNEXCUSED_ABSENCE = {"무단불참", "무단_불참", "unexcused_absence"}


def target_training_hours(
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
) -> int:
    """Return the required hours for a reserve service year."""
    if 1 <= service_year <= 4:
        if mobilization_status in STUDENT:
            return 8
        if mobilization_status in DESIGNATED:
            return 28
        if mobilization_status in NON_DESIGNATED:
            return 28 if branch in NAVY_AIR else 32
        return 0
    if 5 <= service_year <= 6:
        return 20
    return 0


def training_plan(
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
) -> list[dict[str, int | str]]:
    """Return the training components that make up the annual target."""
    if 1 <= service_year <= 4:
        if mobilization_status in STUDENT:
            return [{"name": "기본훈련", "hours": 8}]
        if mobilization_status in DESIGNATED:
            return [{"name": "동원훈련", "hours": 28}]
        if mobilization_status in NON_DESIGNATED:
            if branch in NAVY_AIR:
                return [{"name": "동원훈련Ⅱ형", "hours": 28}]
            return [{"name": "동미참훈련", "hours": 32}]
    if 5 <= service_year <= 6:
        return [
            {"name": "기본훈련", "hours": 8},
            {"name": "작계훈련(전·후반기)", "hours": 12},
        ]
    return []


def completed_training_hours(db: Session, person_id: str, service_year: int) -> int:
    """Sum all recorded training hours for one person and service year."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Education.training_hours), 0)).where(
                Education.person_id == person_id,
                Education.education_year == service_year,
                Education.attendance_status.in_(COMPLETED),
            )
        )
        or 0
    )


def training_progress(
    db: Session,
    person: Person,
    service_year: int,
    carryover_hours: int = 0,
) -> dict[str, object]:
    target = target_training_hours(service_year, person.mobilization_status, person.branch)
    completed = completed_training_hours(db, person.military_number, service_year)
    required = target + carryover_hours
    remaining = max(required - completed, 0)
    latest_round = db.scalar(
        select(func.max(Education.training_round)).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ) or 0
    final_round_absence = db.scalar(
        select(func.count()).where(
            Education.person_id == person.military_number,
            Education.education_year <= service_year,
            Education.training_round >= 3,
            Education.attendance_status.in_(UNEXCUSED_ABSENCE),
        )
    ) or 0
    designated_immediate_risk = (
        1 <= service_year <= 4
        and person.mobilization_status in DESIGNATED
        and db.scalar(
            select(func.count()).where(
                Education.person_id == person.military_number,
                Education.education_year <= service_year,
                Education.attendance_status.in_(UNEXCUSED_ABSENCE),
            )
        )
    )
    prosecution_risk = bool(designated_immediate_risk or final_round_absence > 0)
    return {
        "service_year": service_year,
        "branch": person.branch,
        "mobilization_status": person.mobilization_status,
        "training_plan": training_plan(service_year, person.mobilization_status, person.branch),
        "target_hours": target,
        "carryover_hours": carryover_hours,
        "required_hours": required,
        "completed_hours": completed,
        "remaining_hours": remaining,
        "latest_training_round": int(latest_round),
        "prosecution_risk": prosecution_risk,
        "completed": remaining == 0,
    }


def all_training_progress(db: Session, person: Person) -> list[dict[str, object]]:
    """Return every annual record and roll incomplete hours into the next year."""
    progress: list[dict[str, object]] = []
    carryover = 0
    for service_year in range(0, 9):
        current = training_progress(db, person, service_year, carryover)
        progress.append(current)
        carryover = int(current["remaining_hours"])
    return progress