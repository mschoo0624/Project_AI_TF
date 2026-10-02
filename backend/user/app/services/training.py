"""Annual reserve-training hour rules and progress calculations."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.services.assignment import personnel_category

DESIGNATED = {"지정", "동원지정", "designated"}
NON_DESIGNATED = {"미지정", "동원미지정", "non_designated"}
STUDENT = {"학생", "학생예비군", "student"}
# 동원훈련Ⅰ형: 총 28시간(입영). 동원훈련Ⅱ형: 병 일반 32시간, 공군·간부 28시간.
# 예비군훈련 일부 보류자: hold status independent of designation.
PARTIAL_HOLD = {"보류", "일부보류", "훈련일부보류", "partial_hold"}
COMPLETED = {"이수", "completed"}
ATTENDED = {"참석", "attended"}
UNEXCUSED_ABSENCE = {"무단불참", "무단_불참", "unexcused_absence"}
ROUND_POSTPONED = {"연기", "postponed"}
ROUND_HOLD = {"보류", "round_hold"}
ROUND_SCHEDULED = {"훈련 예정", "scheduled"}
# Any status requiring positive training hours vs. any status that must record zero hours.
ATTENDANCE_HOURS_REQUIRED = COMPLETED | ATTENDED
ATTENDANCE_ZERO_HOURS = UNEXCUSED_ABSENCE | ROUND_POSTPONED | ROUND_HOLD | ROUND_SCHEDULED
TYPE_II_TRAINING_NAMES = {"동원훈련Ⅱ형", "동원훈련II형", "동원훈련2형"}
TYPE_I_TRAINING_NAMES = {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"}
# 부사관/장교는 6년차까지 동원훈련Ⅰ형 대상, 병은 4년차까지만 해당.
OFFICER_CATEGORIES = {"부사관", "장교"}
LOCAL_RESERVE_COMMAND_TITLES = ("기동대부대대장", "부중대장", "소대장")
NON_DESIGNATED_OR_UNSET = NON_DESIGNATED | {None, "해당없음"}

def is_officer_reservist(rank: str | None) -> bool:
    """Return whether a rank belongs to the officer/NCO cadre (간부)."""
    return personnel_category(rank) in OFFICER_CATEGORIES

def is_local_reserve_command_position(position: str | None) -> bool:
    normalized = "".join((position or "").split())
    return any(title in normalized for title in LOCAL_RESERVE_COMMAND_TITLES)

def type_ii_training_hours(
    branch: str | None, rank: str | None, officer_makeup: bool = False
) -> int:
    if officer_makeup and is_officer_reservist(rank):
        return 32
    return 28 if branch == "공군" or is_officer_reservist(rank) else 32

def target_training_hours(
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
    rank: str | None = None,
    position: str | None = None,
) -> int:
    """Return the required hours for a reserve service year."""
    if mobilization_status in STUDENT and 1 <= service_year <= 6:
        return 8
    if (
        1 <= service_year <= 6
        and mobilization_status in NON_DESIGNATED_OR_UNSET
        and is_officer_reservist(rank)
        and is_local_reserve_command_position(position)
    ):
        return 20
    if is_officer_reservist(rank) and 1 <= service_year <= 6:
        return 28
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return 28
        if mobilization_status in NON_DESIGNATED:
            return type_ii_training_hours(branch, rank)
        return 0
    if 5 <= service_year <= 6:
        # 병 5~6년차는 기본훈련과 작계훈련이 기본. 일부보류는 별도 유형이다.
        if mobilization_status in PARTIAL_HOLD:
            return type_ii_training_hours(branch, rank)
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
    position: str | None = None,
    officer_type_ii_makeup: bool = False,
) -> list[dict[str, int | str]]:
    """Return the training components that make up the annual target."""
    if mobilization_status in STUDENT and 1 <= service_year <= 6:
        return [{"name": "학생예비군", "hours": 8}]
    if (
        1 <= service_year <= 6
        and mobilization_status in NON_DESIGNATED_OR_UNSET
        and is_officer_reservist(rank)
        and is_local_reserve_command_position(position)
    ):
        return [
            {"name": "기본훈련", "hours": 8},
            {"name": "작계훈련(전·후반기)", "hours": 12},
        ]
    if is_officer_reservist(rank) and 1 <= service_year <= 6:
        training_type = "동원훈련Ⅰ형" if mobilization_status in DESIGNATED else "동원훈련Ⅱ형"
        hours = 32 if training_type == "동원훈련Ⅱ형" and officer_type_ii_makeup else 28
        return [{"name": training_type, "hours": hours}]
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return [{"name": "동원훈련Ⅰ형", "hours": 28}]
        if mobilization_status in NON_DESIGNATED:
            return [{"name": "동원훈련Ⅱ형", "hours": type_ii_training_hours(branch, rank)}]
        return []
    if 5 <= service_year <= 6:
        if mobilization_status in PARTIAL_HOLD:
            return [{"name": "동원훈련Ⅱ형", "hours": type_ii_training_hours(branch, rank)}]
        return [
            {"name": "기본훈련", "hours": 8},
            {"name": "작계훈련(전·후반기)", "hours": 12},
        ]
    return []


def training_record_required_hours(
    training_type: str, service_year: int, mobilization_status: str | None,
    branch: str | None, rank: str | None, position: str | None = None,
    officer_type_ii_makeup: bool = False,
) -> int | None:
    name = training_type.strip()
    plan = training_plan(
        service_year, mobilization_status, branch, rank, position, officer_type_ii_makeup
    )
    if name in {"동원훈련Ⅱ형", "동원훈련II형", "동원훈련2형"}:
        return type_ii_training_hours(branch, rank, officer_type_ii_makeup)
    if not name or name == "훈련":
        return int(plan[0]["hours"]) if len(plan) == 1 else None
    # A historical record can differ from the person's current annual plan.
    catalog = [
        *training_plan(1, "동원지정", branch, "병장", position),
        *training_plan(1, "동원미지정", branch, "병장", position),
        *training_plan(1, "학생예비군", branch, "병장", position),
        *training_plan(5, "동원지정", branch, "병장", position),
    ]
    return next((int(item["hours"]) for item in [*plan, *catalog] if item["name"] == name), None)


def completed_training_hours(db: Session, person_id: str, service_year: int) -> int:
    """Sum all recorded training hours for one person and service year."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Education.training_hours), 0)).where(
                Education.person_id == person_id,
                Education.education_year == service_year,
                Education.attendance_status.in_(ATTENDANCE_HOURS_REQUIRED),
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


def reconcile_due_training_absences(
    db: Session, person: Person, today: date | None = None
) -> int:
    """Resolve overdue scheduled records unless postponement or hold applies."""
    today = today or date.today()
    scheduled_records = db.scalars(
        select(Education).where(
            Education.person_id == person.military_number,
            Education.attendance_status.in_(ROUND_SCHEDULED),
            Education.scheduled_date.is_not(None),
            Education.scheduled_date < today,
        )
    ).all()
    if not scheduled_records:
        return 0

    postponements = db.scalars(
        select(Postponement).where(
            Postponement.person_id == person.military_number,
            Postponement.status.in_({"pending", "approved"}),
        )
    ).all()
    person_status = (person.status or "").strip().lower()
    changed = 0
    for record in scheduled_records:
        scheduled_date = record.scheduled_date
        if scheduled_date is None:
            continue

        year_status = mobilization_status_for_year(db, person, record.education_year)
        if year_status in PARTIAL_HOLD or person_status in {"hold", "on_hold", "보류"}:
            record.attendance_status = "보류"
        elif year_status in {"연기", "postponed"} or person_status in {"delay", "delayed", "postponed", "연기"}:
            record.attendance_status = "postponed"
        else:
            matching = [
                item for item in postponements
                if item.training_year is None or item.training_year == scheduled_date.year
            ]
            if any(item.status == "pending" for item in matching):
                continue
            approved = [item for item in matching if item.status == "approved"]
            if approved:
                record.attendance_status = (
                    "보류" if any(item.type in {"hold", "보류"} for item in approved)
                    else "postponed"
                )
            else:
                record.attendance_status = "무단불참"
        record.training_hours = 0
        changed += 1

    if changed:
        db.commit()
    return changed


def reconcile_all_due_training_absences(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    person_ids = db.scalars(
        select(Education.person_id)
        .where(
            Education.attendance_status.in_(ROUND_SCHEDULED),
            Education.scheduled_date.is_not(None),
            Education.scheduled_date < today,
        )
        .distinct()
    ).all()
    return sum(
        reconcile_due_training_absences(db, person, today)
        for person_id in person_ids
        if (person := db.get(Person, person_id)) is not None
    )


def officer_type_ii_makeup_required(
    db: Session,
    person: Person,
    service_year: int,
    mobilization_status: str | None,
    carryover_hours: int = 0,
) -> bool:
    eligible_statuses = NON_DESIGNATED_OR_UNSET | PARTIAL_HOLD | {"연기", "postponed"}
    if (
        not is_officer_reservist(person.rank)
        or not 1 <= service_year <= 6
        or mobilization_status in DESIGNATED | STUDENT
        or mobilization_status not in eligible_statuses
        or is_local_reserve_command_position(person.position)
    ):
        return False
    if carryover_hours > 0:
        return True

    records = db.scalars(
        select(Education).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ).all()
    return any(
        record.training_type.replace(" ", "") in TYPE_II_TRAINING_NAMES
        and (
            record.attendance_status in UNEXCUSED_ABSENCE | ROUND_POSTPONED
            or record.training_round >= 2
        )
        for record in records
    )


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


def _normalized_training_type(training_type: str) -> str:
    return "".join(training_type.split())


def absence_recorded(year_records: list[Education]) -> bool:
    return any(record.attendance_status in UNEXCUSED_ABSENCE for record in year_records)


def training_round_escalated(year_records: list[Education]) -> bool:
    return any(
        _normalized_training_type(record.training_type) not in TYPE_I_TRAINING_NAMES
        and (
            (
                record.training_round >= 2
                and record.attendance_status not in ROUND_SCHEDULED
            )
            or (
                record.training_round < 3
                and record.attendance_status in UNEXCUSED_ABSENCE
            )
        )
        for record in year_records
    )


def _prosecutable_failure_reason(
    year_records: list[Education],
    person: Person,
    service_year: int,
    mobilization_status: str | None,
    officer_type_ii_makeup: bool,
) -> str | None:
    """Return only FAQ-backed triggers: Type I absence or an unsatisfied round-3 absence."""
    type_i_absence = next((
        record for record in year_records
        if _normalized_training_type(record.training_type) in TYPE_I_TRAINING_NAMES
        and record.attendance_status in UNEXCUSED_ABSENCE
    ), None)
    if type_i_absence is not None:
        return "동원훈련Ⅰ형 무단불참"

    latest_by_round: dict[tuple[str, int], Education] = {}
    for record in year_records:
        if _normalized_training_type(record.training_type) in TYPE_I_TRAINING_NAMES:
            continue
        key = (_normalized_training_type(record.training_type), record.training_round)
        existing = latest_by_round.get(key)
        if existing is None or record.id > existing.id:
            latest_by_round[key] = record

    for (training_type, training_round), latest in latest_by_round.items():
        if training_round != 3 or latest.attendance_status not in UNEXCUSED_ABSENCE:
            continue
        round_hours = sum(
            record.training_hours
            for record in year_records
            if _normalized_training_type(record.training_type) == training_type
            and record.training_round == training_round
            and record.attendance_status in ATTENDANCE_HOURS_REQUIRED
        )
        required_hours = training_record_required_hours(
            latest.training_type,
            service_year,
            mobilization_status,
            person.branch,
            person.rank,
            person.position,
            officer_type_ii_makeup,
        )
        round_satisfied = (
            round_hours >= required_hours if required_hours is not None
            else round_hours > 0
        )
        if not round_satisfied:
            return f"{latest.training_type} 3차 무단불참"
    return None


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
            if record.attendance_status in ATTENDANCE_HOURS_REQUIRED
        )
        if has_non_postponed_record and completed_hours == 0:
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
    db: Session,
    person: Person,
    service_year: int,
    mobilization_status: str | None,
    officer_type_ii_makeup: bool,
) -> str | None:
    """Return the legal prosecution trigger for one service year, if any."""
    records = db.scalars(
        select(Education).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        ).order_by(Education.training_year, Education.training_round, Education.id)
    ).all()
    return _prosecutable_failure_reason(
        records, person, service_year, mobilization_status, officer_type_ii_makeup
    )


def training_progress(
    db: Session,
    person: Person,
    service_year: int,
    carryover_hours: int = 0,
) -> dict[str, object]:
    mobilization_status = mobilization_status_for_year(db, person, service_year)
    officer_type_ii_makeup = officer_type_ii_makeup_required(
        db, person, service_year, mobilization_status, carryover_hours
    )
    target = target_training_hours(
        service_year, mobilization_status, person.branch, person.rank, person.position
    )
    if officer_type_ii_makeup:
        target = 32
    completed = completed_training_hours(db, person.military_number, service_year)
    required = target + carryover_hours
    remaining = max(required - completed, 0)
    latest_round = db.scalar(
        select(func.max(Education.training_round)).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ) or 0
    year_records = db.scalars(
        select(Education).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ).all()
    absence_is_recorded = absence_recorded(year_records)
    round_is_escalated = training_round_escalated(year_records)
    has_future_scheduled_training = any(
        record.attendance_status in ROUND_SCHEDULED for record in year_records
    )
    absence_streak = consecutive_unexcused_absences(db, person.military_number, service_year)
    current_zero_hours, zero_hour_year_streak, _ = training_completion_risk(
        db, person.military_number, service_year
    )
    prosecution_reason = training_absence_prosecution_reason(
        db, person, service_year, mobilization_status, officer_type_ii_makeup
    )
    prosecution_risk = prosecution_reason is not None
    review_hints = []
    if current_zero_hours:
        review_hints.append("현재 연차 이수시간 없음")
    if absence_streak > 0:
        review_hints.append(f"연속 무단불참 {absence_streak}회")
    if zero_hour_year_streak > 0:
        review_hints.append(f"연속 이수시간 없는 연차 {zero_hour_year_streak}년")
    return {
        "service_year": service_year,
        "branch": person.branch,
        "mobilization_status": mobilization_status,
        "training_plan": training_plan(
            service_year, mobilization_status, person.branch, person.rank, person.position,
            officer_type_ii_makeup,
        ),
        "officer_type_ii_makeup": officer_type_ii_makeup,
        "personnel_category": personnel_category(person.rank),
        "target_hours": target,
        "carryover_hours": carryover_hours,
        "required_hours": required,
        "completed_hours": completed,
        "remaining_hours": remaining,
        "latest_training_round": int(latest_round),
        "absence_recorded": absence_is_recorded,
        "round_escalated": round_is_escalated,
        "prosecution_risk": prosecution_risk,
        "review_hints": review_hints,
        "consecutive_unexcused_absences": absence_streak,
        "current_zero_training_hours": current_zero_hours,
        "consecutive_zero_training_years": zero_hour_year_streak,
        "prosecution_status": "고발대상자" if prosecution_risk else None,
        "prosecution_reason": prosecution_reason,
        "training_status": (
            "훈련 예정" if person.service_year is not None
            and service_year > person.service_year else
            "훈련 예정" if has_future_scheduled_training else
            "훈련 미이수" if required > 0 and remaining > 0 else
            "훈련 이수" if required > 0 else "훈련 대상 아님"
        ),
        "completed": remaining == 0,
    }


def all_training_progress(db: Session, person: Person) -> list[dict[str, object]]:
    """Carry unfinished hours through the end of the enlisted eight-year term."""
    reconcile_due_training_absences(db, person)
    progress: list[dict[str, object]] = []
    carryover = 0
    for service_year in range(0, 9):
        current_carryover = carryover if 1 <= service_year <= 8 else 0
        current = training_progress(db, person, service_year, current_carryover)
        progress.append(current)
        carryover = int(current["remaining_hours"]) if service_year < 8 else 0
    return progress
