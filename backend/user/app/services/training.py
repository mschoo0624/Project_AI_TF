"""Annual reserve-training hour rules and progress calculations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.services.assignment import personnel_category

DESIGNATED = {"지정", "동원지정", "designated"}
NON_DESIGNATED = {"미지정", "동원미지정", "non_designated"}
STUDENT = {"학생", "학생예비군", "student"}
# 예비군훈련 일부 보류자: hold status independent of designation.
PARTIAL_HOLD = {"보류", "일부보류", "훈련일부보류", "partial_hold"}
NAVY_AIR = {"해군", "공군"}
COMPLETED = {"이수", "completed"}
UNEXCUSED_ABSENCE = {"무단불참", "무단_불참", "unexcused_absence"}
# 부사관/장교는 6년차까지 동원훈련Ⅰ형 대상, 병은 4년차까지만 해당.
OFFICER_CATEGORIES = {"부사관", "장교"}

def is_officer_reservist(rank: str | None) -> bool:
    """Return whether a rank belongs to the officer/NCO cadre (간부)."""
    return personnel_category(rank) in OFFICER_CATEGORIES

def target_training_hours(
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
    rank: str | None = None,
) -> int:
    """Return the required hours for a reserve service year."""
    # 간부(부사관/장교)는 동원상태와 무관하게 1~6년차 항상 동원훈련Ⅰ형만 대상이다.
    if is_officer_reservist(rank) and 1 <= service_year <= 6:
        return 28
    if mobilization_status in STUDENT and 1 <= service_year <= 6:
        return 8
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return 28
        if mobilization_status in NON_DESIGNATED:
            return 28 if branch in NAVY_AIR else 32
        return 0
    if 5 <= service_year <= 6:
        # 병의 미지정/일부보류는 동원훈련Ⅱ형 대상이다.
        if mobilization_status in NON_DESIGNATED or mobilization_status in PARTIAL_HOLD:
            return 28 if branch in NAVY_AIR else 32
        # 그 외는 기본훈련 + 작계훈련.
        return 20
    if service_year in (7, 8):
        # 간부는 7~8년차 미이수(훈련 없음), 병은 원래도 대상 외.
        return 0
    return 0


def training_plan(
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
    rank: str | None = None,
) -> list[dict[str, int | str]]:
    """Return the training components that make up the annual target."""
    if is_officer_reservist(rank) and 1 <= service_year <= 6:
        return [{"name": "동원훈련Ⅰ형", "hours": 28}]
    if mobilization_status in STUDENT and 1 <= service_year <= 6:
        return [{"name": "학생예비군", "hours": 8}]
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return [{"name": "동원훈련Ⅰ형", "hours": 28}]
        if mobilization_status in NON_DESIGNATED:
            if branch in NAVY_AIR:
                return [{"name": "동원훈련Ⅱ형", "hours": 28}]
            return [{"name": "동원훈련Ⅱ형", "hours": 32}]
        return []
    if 5 <= service_year <= 6:
        if mobilization_status in NON_DESIGNATED or mobilization_status in PARTIAL_HOLD:
            hours = 28 if branch in NAVY_AIR else 32
            return [{"name": "동원훈련Ⅱ형", "hours": hours}]
        return [
            {"name": "기본훈련", "hours": 8},
            {"name": "작계훈련(전·후반기)", "hours": 12},
        ]
    return []


def training_record_required_hours(
    training_type: str, service_year: int, mobilization_status: str | None,
    branch: str | None, rank: str | None,
) -> int | None:
    """Resolve record requirements from the same plans used for annual targets."""
    name = training_type.strip()
    plan = training_plan(service_year, mobilization_status, branch, rank)
    if not name or name == "훈련":
        return int(plan[0]["hours"]) if len(plan) == 1 else None
    # A historical record can differ from the person's current annual plan.
    catalog = [
        *training_plan(1, "동원지정", branch, "병장"),
        *training_plan(1, "동원미지정", branch, "병장"),
        *training_plan(1, "학생예비군", branch, "병장"),
        *training_plan(5, "동원지정", branch, "병장"),
    ]
    return next((int(item["hours"]) for item in [*plan, *catalog] if item["name"] == name), None)


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


def mobilization_status_for_year(
    db: Session, person: Person, service_year: int
) -> str | None:
    """Return the annual status, deriving legacy assignment status when needed."""
    annual_status = db.scalar(
        select(AnnualStatus.mobilization_status).where(
            AnnualStatus.person_id == person.military_number,
            AnnualStatus.service_year == service_year,
        )
    )
    status = annual_status if annual_status is not None else person.mobilization_status
    if 1 <= service_year <= 6 and annual_status is None:
        if person.squad_id is not None:
            return "동원지정"
        if status in {None, "해당없음"}:
            return "동원미지정"
    return status


def apply_mobilization_status_change(db: Session, person: Person, new_status: str) -> None:
    """Change mobilization status starting the current service year only.

    Years already reached (0..current year - 1) keep whatever status was in
    effect for them, so hours already completed under 동원훈련Ⅱ형/학생예비군/etc.
    are never recomputed retroactively. Only the current year onward switches
    to the new status (e.g. 동원훈련Ⅱ형 이수 후 학생예비군으로 전환).
    """
    old_status = person.mobilization_status or "동원미지정"
    current_year = person.service_year if person.service_year is not None else 0
    current_year = max(0, min(current_year, 8))

    existing = {
        row.service_year: row
        for row in db.scalars(
            select(AnnualStatus).where(AnnualStatus.person_id == person.military_number)
        ).all()
    }

    for year in range(0, current_year):
        if year not in existing:
            db.add(
                AnnualStatus(
                    person_id=person.military_number,
                    service_year=year,
                    mobilization_status=old_status,
                )
            )

    for year in range(current_year, 9):
        row = existing.get(year)
        if row is None:
            db.add(
                AnnualStatus(
                    person_id=person.military_number,
                    service_year=year,
                    mobilization_status=new_status,
                )
            )
        else:
            row.mobilization_status = new_status

    person.mobilization_status = new_status


def consecutive_unexcused_absences(
    db: Session, person_id: str, up_to_year: int | None = None
) -> int:
    """Return the longest chronological run of unexcused training absences."""
    query = select(Education).where(Education.person_id == person_id)
    if up_to_year is not None:
        query = query.where(Education.education_year <= up_to_year)
    records = db.scalars(
        query.order_by(Education.education_year, Education.training_year,
                       Education.training_round, Education.id)
    ).all()
    current = 0
    longest = 0
    for record in records:
        if record.attendance_status in UNEXCUSED_ABSENCE:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def training_completion_risk(
    db: Session, person_id: str, up_to_year: int
) -> tuple[bool, int, bool]:
    """Return current zero-hour status and the longest zero-hour year streak."""
    records = db.scalars(
        select(Education).where(
            Education.person_id == person_id,
            Education.education_year.between(1, up_to_year),
        ).order_by(Education.education_year, Education.id)
    ).all()
    by_year: dict[int, list[Education]] = {}
    for record in records:
        by_year.setdefault(record.education_year, []).append(record)

    zero_hour_years: set[int] = set()
    for year, year_records in by_year.items():
        has_non_postponed_record = any(
            record.attendance_status not in {"연기", "postponed"}
            for record in year_records
        )
        completed_hours = sum(
            record.training_hours
            for record in year_records
            if record.attendance_status in COMPLETED
        )
        has_mobilization_record = any(
            record.training_type.startswith("동원훈련") for record in year_records
        )
        reached_general_threshold = any(record.training_round >= 3 for record in year_records)
        if has_non_postponed_record and completed_hours == 0 and (
            has_mobilization_record or reached_general_threshold
        ):
            zero_hour_years.add(year)

    longest = 0
    current = 0
    for year in range(1, up_to_year + 1):
        if year in zero_hour_years:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return up_to_year in zero_hour_years, longest, bool(zero_hour_years)


def training_absence_prosecution_reason(
    db: Session, person_id: str, up_to_year: int
) -> str | None:
    """Apply criminal referral thresholds to unexcused training absences."""
    records = db.scalars(
        select(Education).where(
            Education.person_id == person_id,
            Education.education_year.between(1, up_to_year),
            Education.attendance_status.in_(UNEXCUSED_ABSENCE),
        ).order_by(Education.education_year, Education.training_year,
                   Education.training_round, Education.id)
    ).all()
    for record in records:
        if record.training_type.startswith("동원훈련"):
            return "동원훈련 무단불참 1회"
        if record.training_round >= 3:
            return "일반 예비군훈련 3차 무단불참"
    return None


def training_progress(
    db: Session,
    person: Person,
    service_year: int,
    carryover_hours: int = 0,
) -> dict[str, object]:
    mobilization_status = mobilization_status_for_year(db, person, service_year)
    target = target_training_hours(service_year, mobilization_status, person.branch, person.rank)
    completed = completed_training_hours(db, person.military_number, service_year)
    required = target + carryover_hours
    remaining = max(required - completed, 0)
    latest_round = db.scalar(
        select(func.max(Education.training_round)).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ) or 0
    absence_streak = consecutive_unexcused_absences(db, person.military_number, service_year)
    current_zero_hours, zero_hour_year_streak, _ = training_completion_risk(
        db, person.military_number, service_year
    )
    absence_prosecution_reason = training_absence_prosecution_reason(
        db, person.military_number, service_year
    )
    is_on_hold = mobilization_status in PARTIAL_HOLD or mobilization_status in {"연기", "postponed"}
    is_current_or_completed_year = (
        person.service_year is not None
        and person.service_year >= 3
        and service_year <= person.service_year
    )
    prosecution_risk = bool(
        is_current_or_completed_year and not is_on_hold and (
            absence_prosecution_reason is not None
            or current_zero_hours
            or zero_hour_year_streak >= 3
        )
    )
    if absence_prosecution_reason is not None:
        prosecution_reason = absence_prosecution_reason
    elif current_zero_hours:
        prosecution_reason = "현재 연차 훈련시간 미이수"
    elif zero_hour_year_streak >= 3:
        prosecution_reason = "3년 연속 훈련시간 미이수"
    else:
        prosecution_reason = None
    return {
        "service_year": service_year,
        "branch": person.branch,
        "mobilization_status": mobilization_status,
        "training_plan": training_plan(service_year, mobilization_status, person.branch, person.rank),
        "personnel_category": personnel_category(person.rank),
        "target_hours": target,
        "carryover_hours": carryover_hours,
        "required_hours": required,
        "completed_hours": completed,
        "remaining_hours": remaining,
        "latest_training_round": int(latest_round),
        "prosecution_risk": prosecution_risk,
        "consecutive_unexcused_absences": absence_streak,
        "current_zero_training_hours": current_zero_hours,
        "consecutive_zero_training_years": zero_hour_year_streak,
        "prosecution_status": "고발대상자" if prosecution_risk else None,
        "prosecution_reason": prosecution_reason,
        "training_status": (
            "훈련 예정" if person.service_year is not None
            and service_year > person.service_year else
            "훈련 미이수" if target > 0 and remaining > 0 else
            "훈련 이수" if target > 0 else "훈련 대상 아님"
        ),
        "completed": remaining == 0,
    }


def all_training_progress(db: Session, person: Person) -> list[dict[str, object]]:
    """Return annual progress and roll incomplete hours through year six only."""
    progress: list[dict[str, object]] = []
    carryover = 0
    for service_year in range(0, 9):
        current_carryover = carryover if 1 <= service_year <= 6 else 0
        current = training_progress(db, person, service_year, current_carryover)
        progress.append(current)
        carryover = int(current["remaining_hours"]) if service_year < 6 else 0
    return progress
