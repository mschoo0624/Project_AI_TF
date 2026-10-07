"""Annual reserve-training hour rules and progress calculations."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.training_schedule import TrainingSession
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
EARLY_DISMISSAL_COUNTS_HOURS = os.getenv(
    "EARLY_DISMISSAL_COUNTS_HOURS", "true"
).lower() in {"1", "true", "yes"}
# Policy defaults are unverified; confirm them against current authoritative guidance.
EARLY_DISMISSAL_ADVANCES_ROUND = os.getenv(
    "EARLY_DISMISSAL_ADVANCES_ROUND", "true"
).lower() in {"1", "true", "yes"}
SMALL_REMAINDER_REVIEW_HOURS = int(os.getenv("SMALL_REMAINDER_REVIEW_HOURS", "8"))
if SMALL_REMAINDER_REVIEW_HOURS < 0:
    raise ValueError("SMALL_REMAINDER_REVIEW_HOURS must be non-negative")
# Any status requiring positive training hours vs. any status that must record zero hours.
ATTENDANCE_HOURS_REQUIRED = COMPLETED | ATTENDED | (
    {"조기퇴소"} if EARLY_DISMISSAL_COUNTS_HOURS else set()
)
ATTENDANCE_ZERO_HOURS = (
    UNEXCUSED_ABSENCE | ROUND_POSTPONED | ROUND_HOLD | ROUND_SCHEDULED
    | (set() if EARLY_DISMISSAL_COUNTS_HOURS else {"조기퇴소"})
)
TYPE_II_TRAINING_NAMES = {"동원훈련Ⅱ형", "동원훈련II형", "동원훈련2형"}
TYPE_I_TRAINING_NAMES = {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"}
# 부사관/장교는 6년차까지 동원훈련Ⅰ형 대상, 병은 4년차까지만 해당.
OFFICER_CATEGORIES = {"부사관", "장교"}
LOCAL_RESERVE_COMMAND_TITLES = ("기동대부대대장", "부중대장", "소대장")
NON_DESIGNATED_OR_UNSET = NON_DESIGNATED | {None, "해당없음"}
OVERDUE_GRACE_DAYS = max(0, int(os.getenv(
    "TRAINING_RESULT_GRACE_DAYS", os.getenv("TRAINING_OVERDUE_GRACE_DAYS", "7")
)))
KOREA = ZoneInfo("Asia/Seoul")


def _today_korea() -> date:
    return datetime.now(timezone.utc).astimezone(KOREA).date()


def training_last_session_days(db: Session, records: list[Education]) -> dict[int, date | None]:
    schedule_ids = {record.schedule_id for record in records if record.schedule_id is not None}
    last_days = {}
    if schedule_ids:
        last_days = dict(db.execute(
            select(TrainingSession.schedule_id, func.max(TrainingSession.session_date))
            .where(TrainingSession.schedule_id.in_(schedule_ids))
            .group_by(TrainingSession.schedule_id)
        ).all())
    return {
        record.id: last_days.get(record.schedule_id, record.scheduled_date)
        for record in records
    }

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
    officer_type_ii_makeup: bool = False,
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
        if mobilization_status in DESIGNATED:
            return 28
        return type_ii_training_hours(branch, rank, officer_type_ii_makeup)
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return 28
        if mobilization_status in NON_DESIGNATED:
            return type_ii_training_hours(branch, rank, officer_type_ii_makeup)
        return 0
    if 5 <= service_year <= 6:
        # 병 5~6년차는 기본훈련과 작계훈련이 기본. 일부보류는 별도 유형이다.
        if mobilization_status in PARTIAL_HOLD:
            return type_ii_training_hours(branch, rank, officer_type_ii_makeup)
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
        hours = 28 if training_type == "동원훈련Ⅰ형" else type_ii_training_hours(
            branch, rank, officer_type_ii_makeup
        )
        return [{"name": training_type, "hours": hours}]
    if 1 <= service_year <= 4:
        if mobilization_status in DESIGNATED:
            return [{"name": "동원훈련Ⅰ형", "hours": 28}]
        if mobilization_status in NON_DESIGNATED:
            return [{"name": "동원훈련Ⅱ형", "hours": type_ii_training_hours(
                branch, rank, officer_type_ii_makeup
            )}]
        return []
    if 5 <= service_year <= 6:
        if mobilization_status in PARTIAL_HOLD:
            return [{"name": "동원훈련Ⅱ형", "hours": type_ii_training_hours(
                branch, rank, officer_type_ii_makeup
            )}]
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
                Education.source_kind != "estimated",
            )
        )
        or 0
    )


def _approved_excusal_record_ids(
    db: Session, person_id: str, records: list[Education]
) -> set[int]:
    excusals = db.scalars(select(Postponement).where(
        Postponement.person_id == person_id,
        Postponement.status == "approved",
        Postponement.type.in_({"delay", "연기", "hold", "보류", "법규보류", "방침보류"}),
    )).all()
    excluded: set[int] = set()
    for record in records:
        for item in excusals:
            linked = item.education_record_id == record.id
            in_period = (
                record.scheduled_date is not None
                and item.start_date is not None
                and item.end_date is not None
                and item.start_date <= record.scheduled_date <= item.end_date
                and (item.training_year is None or item.training_year == record.training_year)
            )
            if linked or in_period:
                excluded.add(record.id)
                break
    return excluded


def _approved_deferral_record_ids(
    db: Session, person_id: str, records: list[Education]
) -> set[int]:
    rows = db.scalars(select(Postponement).where(
        Postponement.person_id == person_id,
        Postponement.status == "approved",
        Postponement.type.in_({"delay", "연기"}),
    )).all()
    approved: set[int] = set()
    for record in records:
        for item in rows:
            linked = item.education_record_id == record.id
            in_period = (
                record.scheduled_date is not None
                and item.start_date is not None
                and item.end_date is not None
                and item.start_date <= record.scheduled_date <= item.end_date
                and (item.training_year is None or item.training_year == record.training_year)
            )
            if linked or in_period:
                approved.add(record.id)
                break
    return approved


def mobilization_status_for_year(
    db: Session, person: Person, service_year: int
) -> str | None:
    """Return the recorded annual status without inferring it from assignment."""
    annual_status = db.scalar(
        select(AnnualStatus.mobilization_status).where(
            AnnualStatus.person_id == person.military_number,
            AnnualStatus.service_year == service_year,
        )
    )
    return annual_status if annual_status is not None else person.mobilization_status


def reconcile_due_training_absences(
    db: Session, person: Person, today: date | None = None
) -> int:
    """Count overdue scheduled records without inferring an attendance result."""
    today = today or _today_korea()
    scheduled_records = db.scalars(
            select(Education).where(
            Education.person_id == person.military_number,
            Education.attendance_status.in_(ROUND_SCHEDULED),
            Education.scheduled_date.is_not(None),
        )
    ).all()
    last_days = training_last_session_days(db, scheduled_records)
    return sum(
        last_day is not None and today > last_day + timedelta(days=OVERDUE_GRACE_DAYS)
        for record in scheduled_records
        if (last_day := last_days.get(record.id)) is not None
    )


def reconcile_all_due_training_absences(db: Session, today: date | None = None) -> int:
    today = today or _today_korea()
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
    if not is_officer_reservist(person.rank) or not training_plan_has_type(
        "동원훈련Ⅱ형",
        service_year,
        mobilization_status,
        person.branch,
        person.rank,
        person.position,
    ):
        return False
    if carryover_hours > 0:
        return True

    records = db.scalars(select(Education).where(
        Education.person_id == person.military_number,
        Education.education_year == service_year,
    )).all()
    type_ii_records = [
        record for record in records
        if _normalized_training_type(record.training_type) == "동원훈련Ⅱ형"
    ]
    approved_deferrals = _approved_deferral_record_ids(
        db, person.military_number, type_ii_records
    )
    escalated_attempts = sum(
        (
            record.attendance_status in UNEXCUSED_ABSENCE and bool(record.confirmed_by)
        ) or (
            record.attendance_status in ROUND_POSTPONED and record.id in approved_deferrals
        )
        for record in type_ii_records
    )
    return escalated_attempts >= 2


def apply_mobilization_status_change(db: Session, person: Person, new_status: str) -> None:
    """Change mobilization status starting the current service year only.

    Years already reached (0..current year - 1) keep whatever status was in
    effect for them, so hours already completed under 동원훈련Ⅱ형/학생예비군/etc.
    are never recomputed retroactively. Only the current year onward switches
    to the new status (e.g. 동원훈련Ⅱ형 이수 후 학생예비군으로 전환).
    """
    old_status = person.mobilization_status or "동원미지정"
    current_year = person.service_year if person.service_year is not None else 0
    current_year = max(0, current_year)

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

    for year in range(current_year, max(9, current_year + 1)):
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
    excluded = _approved_excusal_record_ids(db, person_id, records)
    current = 0
    longest = 0
    for record in records:
        if (
            record.id not in excluded
            and record.attendance_status in UNEXCUSED_ABSENCE
            and bool(record.confirmed_by)
        ):
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _normalized_training_type(training_type: str) -> str:
    normalized = "".join(training_type.split())
    if normalized in TYPE_I_TRAINING_NAMES:
        return "동원훈련Ⅰ형"
    if normalized in TYPE_II_TRAINING_NAMES:
        return "동원훈련Ⅱ형"
    return normalized


def training_plan_has_type(
    training_type: str,
    service_year: int,
    mobilization_status: str | None,
    branch: str | None = None,
    rank: str | None = None,
    position: str | None = None,
) -> bool:
    target = _normalized_training_type(training_type)
    plan = training_plan(service_year, mobilization_status, branch, rank, position)
    return any(_normalized_training_type(str(item["name"])) == target for item in plan)


def training_round_satisfied(
    attendance_status: str, training_hours: int, required_hours: int | None
) -> bool:
    if attendance_status not in ATTENDANCE_HOURS_REQUIRED:
        return False
    return training_hours > 0 if required_hours is None else training_hours >= required_hours


def training_round_sequence_error(
    records: list[Education],
    training_type: str,
    training_round: int | None,
    attendance_status: str | None,
    training_hours: int,
    required_hours: int | None,
    exclude_record_id: int | None = None,
    approved_deferral_record_ids: set[int] | None = None,
    attempt_confirmed: bool = False,
) -> str | None:
    training_type_key = _normalized_training_type(training_type)
    approved_deferral_record_ids = approved_deferral_record_ids or set()
    attempts = [
        (
            record.id,
            record.training_round,
            record.attendance_status,
            record.training_hours,
            bool(record.confirmed_by),
            record.id in approved_deferral_record_ids,
        )
        for record in records
        if record.id != exclude_record_id
        and _normalized_training_type(record.training_type) == training_type_key
    ]
    if training_round is not None and attendance_status is not None:
        attempts.append((None, training_round, attendance_status, training_hours, attempt_confirmed, False))

    rounds: dict[int, tuple[int | None, str, int, bool, bool]] = {}
    for record_id, round_number, status, hours, confirmed, approved_deferral in attempts:
        if round_number in rounds:
            return f"{training_type_key} {round_number}차 기록이 이미 있습니다. 기존 기록을 수정하세요."
        rounds[round_number] = (record_id, status, hours, confirmed, approved_deferral)

    if training_type_key in TYPE_I_TRAINING_NAMES and any(round_number != 1 for round_number in rounds):
        return "동원훈련Ⅰ형은 1차 기록만 등록할 수 있습니다."

    if training_type_key not in TYPE_I_TRAINING_NAMES:
        for round_number in (2, 3):
            current = rounds.get(round_number)
            if current is None:
                continue
            previous = rounds.get(round_number - 1)
            if previous is None:
                return f"{round_number}차 전에 {round_number - 1}차 기록이 필요합니다."
            _, previous_status, previous_hours, confirmed, approved_deferral = previous
            if (
                previous_status in UNEXCUSED_ABSENCE and confirmed
            ) or approved_deferral:
                continue
            if training_round_satisfied(previous_status, previous_hours, required_hours):
                return f"{round_number - 1}차 훈련이 이미 충족되어 {round_number}차 기록은 등록할 수 없습니다."
            if (
                EARLY_DISMISSAL_ADVANCES_ROUND
                and previous_status == "조기퇴소"
                and 0 < previous_hours < (required_hours or 0)
            ):
                continue
            return (
                f"{round_number}차는 {round_number - 1}차 무단불참, 연기 또는 "
                "미이수 조기퇴소 후에만 등록할 수 있습니다."
            )
    return None


def absence_recorded(year_records: list[Education]) -> bool:
    return any(
        record.attendance_status in UNEXCUSED_ABSENCE and bool(record.confirmed_by)
        for record in year_records
    )


def training_round_escalated(
    year_records: list[Education], approved_deferral_record_ids: set[int] | None = None
) -> bool:
    approved_deferral_record_ids = approved_deferral_record_ids or set()
    if any(
        _normalized_training_type(record.training_type) not in TYPE_I_TRAINING_NAMES
        and record.training_round < 3
        and (
            (record.attendance_status in UNEXCUSED_ABSENCE and bool(record.confirmed_by))
            or record.id in approved_deferral_record_ids
        )
        for record in year_records
    ):
        return True
    latest_by_round: dict[tuple[str, int], Education] = {}
    for record in year_records:
        training_type = _normalized_training_type(record.training_type)
        if training_type in TYPE_I_TRAINING_NAMES:
            continue
        key = (training_type, record.training_round)
        if key not in latest_by_round or record.id > latest_by_round[key].id:
            latest_by_round[key] = record
    return any(
        (training_type, round_number - 1) in latest_by_round
        and (
            (
                latest_by_round[(training_type, round_number - 1)].attendance_status
                in UNEXCUSED_ABSENCE
                and bool(latest_by_round[(training_type, round_number - 1)].confirmed_by)
            )
            or latest_by_round[(training_type, round_number - 1)].id in approved_deferral_record_ids
        )
        for training_type, round_number in latest_by_round
        if round_number >= 2
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
        and bool(record.confirmed_by)
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
        if (
            training_round != 3
            or latest.attendance_status not in UNEXCUSED_ABSENCE
            or not latest.confirmed_by
        ):
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
    excluded = _approved_excusal_record_ids(db, person_id, records)
    records = [record for record in records if record.id not in excluded]
    by_year: dict[int, list[Education]] = {}
    for record in records:
        by_year.setdefault(record.education_year, []).append(record)

    zero_hour_years: set[int] = set()
    for year, year_records in by_year.items():
        has_non_postponed_record = any(
            record.attendance_status not in {"연기", "postponed"}
            and not (record.attendance_status in UNEXCUSED_ABSENCE and not record.confirmed_by)
            for record in year_records
        )
        completed_hours = sum(
            record.training_hours
            for record in year_records
            if record.attendance_status in ATTENDANCE_HOURS_REQUIRED
            and record.source_kind != "estimated"
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
    records = [
        record for record in records
        if record.id not in _approved_excusal_record_ids(db, person.military_number, records)
    ]
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
    annual_semester_completed = db.scalar(
        select(AnnualStatus.semester_completed).where(
            AnnualStatus.person_id == person.military_number,
            AnnualStatus.service_year == service_year,
        )
    )
    student_semester_missing = mobilization_status in STUDENT and annual_semester_completed is None
    designation_review = 1 <= service_year <= 6 and mobilization_status in {None, "해당없음"}
    if mobilization_status in STUDENT and annual_semester_completed is False:
        if person.mobilization_status in DESIGNATED | NON_DESIGNATED:
            mobilization_status = person.mobilization_status
        else:
            mobilization_status = None
            designation_review = True
    officer_type_ii_makeup = officer_type_ii_makeup_required(
        db, person, service_year, mobilization_status, carryover_hours
    )
    target = target_training_hours(
        service_year, mobilization_status, person.branch, person.rank, person.position,
        officer_type_ii_makeup,
    )
    needs_review_reason = (
        "student_semester_data_missing" if student_semester_missing
        else "missing_designated_status" if designation_review
        else None
    )
    if needs_review_reason:
        target = 0
    completed = completed_training_hours(db, person.military_number, service_year)
    required = target + carryover_hours
    remaining = max(required - completed, 0)
    displayed_carryover = carryover_hours
    if needs_review_reason:
        completed = 0
        required = 0
        remaining = 0
        displayed_carryover = 0
    latest_round = db.scalar(
        select(func.max(Education.training_round)).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ) or 0
    all_year_records = db.scalars(
        select(Education).where(
            Education.person_id == person.military_number,
            Education.education_year == service_year,
        )
    ).all()
    excluded = _approved_excusal_record_ids(db, person.military_number, all_year_records)
    year_records = [record for record in all_year_records if record.id not in excluded]
    unconfirmed_absence_count = sum(
        record.attendance_status in UNEXCUSED_ABSENCE
        and not record.confirmed_by
        and record.id not in excluded
        for record in all_year_records
    )
    absence_is_recorded = absence_recorded(year_records)
    round_is_escalated = training_round_escalated(
        all_year_records,
        _approved_deferral_record_ids(db, person.military_number, all_year_records),
    )
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
    if needs_review_reason:
        review_hints.append(needs_review_reason)
    if unconfirmed_absence_count:
        review_hints.append(f"무단불참 확인자 정보 누락 {unconfirmed_absence_count}건 (보완 필요)")
    overdue_count = reconcile_due_training_absences(db, person, _today_korea())
    if current_zero_hours:
        review_hints.append("현재 연차 이수시간 없음")
    if absence_streak > 0:
        review_hints.append(f"연속 무단불참 {absence_streak}회")
    if zero_hour_year_streak > 0:
        review_hints.append(f"연속 이수시간 없는 연차 {zero_hour_year_streak}년")
    if overdue_count:
        review_hints.append(f"훈련 결과 미입력 {overdue_count}건 (확인 필요)")
    return {
        "service_year": service_year,
        "branch": person.branch,
        "mobilization_status": mobilization_status,
        "training_plan": [] if needs_review_reason else training_plan(
            service_year, mobilization_status, person.branch, person.rank, person.position,
            officer_type_ii_makeup,
        ),
        "officer_type_ii_makeup": officer_type_ii_makeup,
        "personnel_category": personnel_category(person.rank),
        "target_hours": target,
        "carryover_hours": displayed_carryover,
        "required_hours": required,
        "completed_hours": completed,
        "remaining_hours": remaining,
        "latest_training_round": int(latest_round),
        "absence_recorded": absence_is_recorded,
        "unconfirmed_absence_count": unconfirmed_absence_count,
        "round_escalated": round_is_escalated,
        "prosecution_risk": prosecution_risk,
        "review_hints": review_hints,
        "consecutive_unexcused_absences": absence_streak,
        "current_zero_training_hours": current_zero_hours,
        "consecutive_zero_training_years": zero_hour_year_streak,
        "prosecution_status": "고발대상자" if prosecution_risk else None,
        "prosecution_reason": prosecution_reason,
        "needs_review_reason": needs_review_reason,
        "training_status": (
            "NEEDS_REVIEW" if needs_review_reason else
            "훈련 예정" if person.service_year is not None
            and service_year > person.service_year else
            "훈련 예정" if has_future_scheduled_training else
            "훈련 미이수" if required > 0 and remaining > 0 else
            "훈련 이수" if required > 0 else "훈련 대상 아님"
        ),
        "completed": remaining == 0,
    }


def all_training_progress(db: Session, person: Person) -> list[dict[str, object]]:
    """Carry unfinished hours through year eight and any later officer service years."""
    progress: list[dict[str, object]] = []
    carryover = 0
    last_year = max(8, person.service_year or 0)
    for service_year in range(0, last_year + 1):
        current_carryover = carryover if service_year > 0 else 0
        current = training_progress(db, person, service_year, current_carryover)
        progress.append(current)
        carryover = int(current["remaining_hours"])
    from user.app.services.training_recalculation import overlay_progress_with_recalculation

    return overlay_progress_with_recalculation(db, person, progress)
