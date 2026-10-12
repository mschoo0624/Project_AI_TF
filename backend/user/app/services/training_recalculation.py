"""Deterministic rebuild of reserve-training obligations and carryover state."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select, text
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.training_recalculation import (
    TrainingCarryover,
    TrainingCarryoverResolution,
    TrainingRoundState,
    TrainingRolloverRun,
    TrainingStatusPolicy,
    TrainingYearResult,
)
from user.app.services.training import (
    ATTENDED,
    COMPLETED,
    DESIGNATED,
    EARLY_DISMISSAL_ADVANCES_ROUND,
    EARLY_DISMISSAL_COUNTS_HOURS,
    NON_DESIGNATED,
    PARTIAL_HOLD,
    STUDENT,
    TYPE_I_TRAINING_NAMES,
    TYPE_II_TRAINING_NAMES,
    UNEXCUSED_ABSENCE,
    all_training_progress,
    is_officer_reservist,
    is_local_reserve_command_position,
    training_plan,
    training_record_required_hours,
)

YEAR_END_MONTH = int(os.getenv("TRAINING_OBLIGATION_YEAR_END_MONTH", "12"))
YEAR_END_DAY = int(os.getenv("TRAINING_OBLIGATION_YEAR_END_DAY", "31"))
TYPE1_DEFERRAL_CONVERTS_TO_TYPE2 = os.getenv(
    "TRAINING_TYPE1_DEFERRAL_CONVERTS_TO_TYPE2", "true"
).lower() in {"1", "true", "yes"}
LEGACY_SERVICE_YEAR_FALLBACK = os.getenv(
    "TRAINING_LEGACY_SERVICE_YEAR_FALLBACK", "true"
).lower() in {"1", "true", "yes"}
OVERSEAS_HOLD_MIN_DAYS = int(os.getenv("TRAINING_OVERSEAS_HOLD_MIN_DAYS", "365"))
ILLNESS_HOLD_MIN_DAYS = int(os.getenv("TRAINING_ILLNESS_HOLD_MIN_DAYS", "180"))
MOBILIZATION_DEFERRAL_LIMIT = int(os.getenv("TRAINING_MOBILIZATION_DEFERRAL_LIMIT", "2"))
GENERAL_DEFERRAL_LIMIT = int(os.getenv("TRAINING_GENERAL_DEFERRAL_LIMIT", "6"))
HOLD_RESOLUTION_GRACE_DAYS = int(os.getenv("TRAINING_HOLD_RESOLUTION_GRACE_DAYS", "14"))
DEFERRAL_COUNTER_SCOPE = os.getenv("TRAINING_DEFERRAL_COUNTER_SCOPE", "reserve_period")
MOBILIZATION_DEFERRAL_REASONS = tuple(
    item.strip().lower()
    for item in os.getenv(
        "TRAINING_MOBILIZATION_DEFERRAL_REASONS",
        "중요업무,주요업무,시험,자격시험,해외여행,직업훈련,주요행사,major_work,license_exam,planned_travel_abroad,vocational_school,major_event",
    ).split(",")
    if item.strip()
)
KOREA = ZoneInfo("Asia/Seoul")


def _today_korea() -> date:
    return datetime.now(KOREA).date()

DEFAULT_STATUS_POLICIES: dict[str, dict[str, object]] = {
    "조기퇴소": {
        "counts_hours": EARLY_DISMISSAL_COUNTS_HOURS,
        "credits_hours": False,
        "advances_round": False,
        "confirmed_absence": False,
        "prosecution_kind": None,
    },
    **{
        status: {
            "counts_hours": True,
            "credits_hours": False,
            "advances_round": False,
            "confirmed_absence": False,
            "prosecution_kind": None,
        }
        for status in ("이수", "completed", "참석", "attended")
    },
    **{
        status: {
            "counts_hours": False,
            "credits_hours": False,
            "advances_round": True,
            "confirmed_absence": True,
            "prosecution_kind": "type_i_or_round_3",
        }
        for status in ("무단불참", "무단_불참", "unexcused_absence")
    },
    **{
        status: {
            "counts_hours": False,
            "credits_hours": False,
            "advances_round": False,
            "confirmed_absence": False,
            "prosecution_kind": None,
        }
        for status in ("연기", "postponed", "보류", "round_hold", "훈련 예정", "scheduled", "overdue")
    },
}


@dataclass
class _Debt:
    person_id: str
    origin_year: int
    training_type: str
    origin_round: int
    current_round: int
    original_hours: int
    remaining_hours: int
    status: str
    reason_code: str | None = None
    converted_from_type: str | None = None


@dataclass(frozen=True)
class _Allocation:
    debt_key: tuple[int, str, int]
    education_id: int
    hours: int


def service_year_for_date(base_date: date, today: date | None = None) -> int:
    """Count the discharge year as year zero and the next calendar year as year one."""
    today = today or _today_korea()
    return max(0, today.year - base_date.year)


def obligation_calendar_year(
    service_year: int,
    base_date: date | None,
    current_service_year: int,
    today: date | None = None,
) -> int:
    """Map an obligation year to its calendar year without conflating training_year."""
    today = today or _today_korea()
    if base_date is not None:
        return base_date.year + service_year
    return today.year - (current_service_year - service_year)


def obligation_year_is_closed(
    service_year: int,
    base_date: date | None,
    current_service_year: int,
    today: date | None = None,
) -> bool:
    """Close an obligation only after its configured calendar end date has passed."""
    today = today or _today_korea()
    year = obligation_calendar_year(service_year, base_date, current_service_year, today)
    end = date(year, YEAR_END_MONTH, YEAR_END_DAY)
    return today > end


def _base_date(person: Person) -> date | None:
    origin = (person.origin_type or "").replace(" ", "")
    if "상근" in origin:
        return person.callup_release_date or person.discharge_date
    return person.discharge_date


def _current_service_year(person: Person, today: date) -> tuple[int, str | None]:
    base_date = _base_date(person)
    if base_date is not None:
        return service_year_for_date(base_date, today), None
    if LEGACY_SERVICE_YEAR_FALLBACK and person.service_year is not None:
        return max(0, person.service_year), None
    return max(0, person.service_year or 0), "missing_discharge_date"


def _training_type_key(name: str) -> str:
    compact = "".join(name.split())
    if compact in TYPE_I_TRAINING_NAMES:
        return "동원훈련Ⅰ형"
    if compact in TYPE_II_TRAINING_NAMES:
        return "동원훈련Ⅱ형"
    if compact in {"학생예비군", "학생훈련"}:
        return "기본훈련"
    if compact.startswith("작계훈련"):
        return "작계훈련"
    return name.strip()


def _status_policy_map(db: Session) -> dict[str, dict[str, object]]:
    policies = {key: dict(value) for key, value in DEFAULT_STATUS_POLICIES.items()}
    for row in db.scalars(select(TrainingStatusPolicy)).all():
        if row.enabled:
            policies[row.status_key] = {
                "counts_hours": row.counts_hours,
                "credits_hours": row.credits_hours,
                "advances_round": row.advances_round,
                "confirmed_absence": row.confirmed_absence,
                "prosecution_kind": row.prosecution_kind,
            }
        else:
            policies.pop(row.status_key, None)
    return policies


def _mobilization_status(
    db: Session, person: Person, service_year: int
) -> tuple[str | None, bool | None]:
    annual = db.get(AnnualStatus, (person.military_number, service_year))
    if annual is not None:
        return annual.mobilization_status, annual.semester_completed
    return person.mobilization_status, None


def _hold_is_eligible(postponement: Postponement) -> bool:
    duration = 0
    if postponement.start_date and postponement.end_date:
        duration = (postponement.end_date - postponement.start_date).days + 1
    reason = f"{postponement.reason} {postponement.category or ''}".lower()
    if "해외" in reason or "overseas" in reason:
        return duration >= OVERSEAS_HOLD_MIN_DAYS
    if "질병" in reason or "illness" in reason or "medical" in reason:
        return bool(postponement.source_file) and duration >= ILLNESS_HOLD_MIN_DAYS
    return True


def postponement_limit_warnings(
    db: Session, person_id: str, today: date | None = None
) -> list[str]:
    today = today or _today_korea()
    rows = db.scalars(select(Postponement).where(
        Postponement.person_id == person_id,
        Postponement.status == "approved",
    )).all()
    delay_rows = [row for row in rows if (row.type or "").lower() in {"delay", "연기"}]
    if DEFERRAL_COUNTER_SCOPE == "calendar_year":
        delay_rows = [row for row in delay_rows if row.training_year == today.year]
    limited = sum(
        any(token in f"{row.category or ''} {row.reason}".lower() for token in MOBILIZATION_DEFERRAL_REASONS)
        for row in delay_rows
    )
    warnings = []
    if limited >= MOBILIZATION_DEFERRAL_LIMIT:
        warnings.append("mobilization_deferral_limit_reached")
    if len(delay_rows) >= GENERAL_DEFERRAL_LIMIT:
        warnings.append("general_deferral_limit_reached")
    for row in rows:
        is_hold = (row.type or "").lower() in {"hold", "보류", "법규보류", "방침보류"}
        if is_hold and row.end_date and today > row.end_date + timedelta(days=HOLD_RESOLUTION_GRACE_DAYS) and not row.resolution_reported_at:
            warnings.append(f"hold_resolution_report_overdue:{row.id}")
    return sorted(set(warnings))


def _approved_for_record(
    postponements: list[Postponement], record: Education, kind: str
) -> list[Postponement]:
    selected: list[Postponement] = []
    for item in postponements:
        if item.status != "approved":
            continue
        item_type = (item.type or "").lower()
        is_hold = item_type in {"hold", "보류", "법규보류", "방침보류"}
        eligible_hold = is_hold and _hold_is_eligible(item)
        is_deferral = item_type in {"delay", "연기"} or (is_hold and not eligible_hold)
        if (kind == "hold" and not eligible_hold) or (kind == "delay" and not is_deferral):
            continue
        linked = item.education_record_id == record.id
        in_period = (
            record.scheduled_date is not None
            and item.start_date is not None
            and item.end_date is not None
            and item.start_date <= record.scheduled_date <= item.end_date
        )
        same_training_year = item.training_year is None or item.training_year == record.training_year
        if linked or (in_period and same_training_year):
            selected.append(item)
    return selected


def _rounds_for_person(
    db: Session, person: Person, records: list[Education], postponements: list[Postponement],
    policies: dict[str, dict[str, object]], progress: list[dict[str, object]],
) -> dict[tuple[int, str], int]:
    advances: dict[tuple[int, str], int] = {}
    approved_deferrals = {
        item.education_record_id
        for item in postponements
        if item.status == "approved"
        and (
            (item.type or "").lower() in {"delay", "연기"}
            or ((item.type or "").lower() in {"hold", "보류", "법규보류", "방침보류"}
                and not _hold_is_eligible(item))
        )
    }
    ordered = sorted(records, key=lambda row: (row.education_year, row.training_year or 0, row.id))
    for record in ordered:
        training_type = _training_type_key(record.training_type)
        is_approved_deferral = (
            record.id in approved_deferrals
            or bool(_approved_for_record(postponements, record, "delay"))
        )
        if (
            training_type == "동원훈련Ⅰ형"
            and is_approved_deferral
            and TYPE1_DEFERRAL_CONVERTS_TO_TYPE2
        ):
            training_type = "동원훈련Ⅱ형"
        elif training_type == "동원훈련Ⅰ형":
            continue
        round_key = (record.education_year, training_type)
        policy = policies.get(record.attendance_status)
        if policy is None:
            continue
        confirmed = bool(record.confirmed_by)
        advances_round = bool(policy["advances_round"]) and confirmed
        advances_round = advances_round or is_approved_deferral
        if (
            EARLY_DISMISSAL_ADVANCES_ROUND
            and training_type == "동원훈련Ⅱ형"
            and record.attendance_status == "조기퇴소"
        ):
            mobilization_status, _ = _mobilization_status(db, person, record.education_year)
            year_progress = (
                progress[record.education_year]
                if 0 <= record.education_year < len(progress)
                else None
            )
            required_hours = training_record_required_hours(
                record.training_type,
                record.education_year,
                mobilization_status,
                person.branch,
                person.rank,
                person.position,
                bool(year_progress and year_progress.get("officer_type_ii_makeup")),
            )
            advances_round = advances_round or (
                required_hours is not None
                and 0 < record.training_hours < required_hours
            )
        if advances_round:
            advances[round_key] = min(3, max(advances.get(round_key, 1), record.training_round + 1))
        else:
            advances.setdefault(round_key, max(1, record.training_round))
    return advances


def recalculate_person(
    db: Session,
    person_id: str,
    from_year: int = 1,
    reason: str = "manual",
    actor: str = "system",
    today: date | None = None,
    actor_user_id: int | None = None,
) -> dict[str, object]:
    """Rebuild one person's derived training state; caller commits the transaction.

    The calculation always replays from year one so edits to old records cannot
    leave stale carryover. Stable carryover keys and deterministic allocation
    make repeated calls produce the same derived rows.
    """
    person = db.get(Person, person_id)
    if person is None:
        raise ValueError("Reservist not found")
    today = today or _today_korea()
    current_year, date_review = _current_service_year(person, today)
    current_year = max(0, current_year)
    base_date = _base_date(person)
    if base_date is not None and person.service_year != current_year:
        person.service_year = current_year
    policies = _status_policy_map(db)
    records = list(db.scalars(
        select(Education).where(Education.person_id == person_id)
        .order_by(Education.education_year, Education.training_year, Education.id)
    ).all())
    postponements = list(db.scalars(
        select(Postponement).where(Postponement.person_id == person_id)
    ).all())
    imported_rows = list(db.scalars(
        select(TrainingCarryover).where(
            TrainingCarryover.person_id == person_id,
            TrainingCarryover.imported_hours > 0,
        )
    ).all())
    progress = all_training_progress(db, person)
    rounds = _rounds_for_person(db, person, records, postponements, policies, progress)
    records_by_year_type: dict[tuple[int, str], list[Education]] = {}
    for record in records:
        key = (record.education_year, _training_type_key(record.training_type))
        records_by_year_type.setdefault(key, []).append(record)

    debt_by_key: dict[tuple[int, str, int], _Debt] = {}
    allocations: list[_Allocation] = []
    result_values: dict[tuple[int, str], dict[str, object]] = {}
    pending_demands: list[_Debt] = []
    carried_count_by_year: dict[int, int] = {}
    seeded_imports: set[tuple[int, str, int]] = set()

    for service_year in range(1, current_year + 1):
        for imported in imported_rows:
            key = (imported.origin_year, imported.training_type, imported.origin_round)
            if imported.origin_year >= service_year or key in seeded_imports:
                continue
            existing_debt = debt_by_key.get(key)
            if existing_debt is not None:
                seeded_imports.add(key)
                continue
            debt = _Debt(
                person_id=person_id,
                origin_year=imported.origin_year,
                training_type=imported.training_type,
                origin_round=imported.origin_round,
                current_round=imported.current_round,
                original_hours=imported.imported_hours,
                remaining_hours=imported.imported_hours,
                status="open",
                reason_code="transfer_import",
            )
            debt_by_key[key] = debt
            pending_demands.append(debt)
            seeded_imports.add(key)
        status, semester_completed = _mobilization_status(db, person, service_year)
        review_reason: str | None = date_review
        year_records = [row for row in records if row.education_year == service_year]
        if any(row.attendance_status not in policies for row in year_records):
            review_reason = review_reason or "unknown_attendance_status"
        known_training_types = {"동원훈련Ⅰ형", "동원훈련Ⅱ형", "기본훈련", "작계훈련"}
        if any(_training_type_key(row.training_type) not in known_training_types for row in year_records):
            review_reason = review_reason or "unknown_training_type"
        if status is None:
            review_reason = review_reason or "missing_designated_status"
        elif status not in DESIGNATED | NON_DESIGNATED | STUDENT | PARTIAL_HOLD | {"해당없음", "지정", "미지정"}:
            review_reason = review_reason or "unknown_mobilization_status"

        effective_status = status
        if status in STUDENT:
            if semester_completed is None:
                review_reason = review_reason or "student_semester_data_missing"
            elif semester_completed is False:
                if person.mobilization_status in DESIGNATED | NON_DESIGNATED:
                    effective_status = person.mobilization_status
                else:
                    review_reason = review_reason or "missing_designated_status"
                    effective_status = None

        plan = training_plan(
            service_year,
            effective_status,
            person.branch,
            person.rank,
            person.position,
        ) if review_reason is None or review_reason == date_review else []
        targets: dict[str, int] = {}
        for component in plan:
            training_type = _training_type_key(str(component["name"]))
            targets[training_type] = targets.get(training_type, 0) + int(component["hours"])

        if review_reason:
            result_values[(service_year, "NEEDS_REVIEW")] = {
                "required_hours": 0,
                "counted_hours": 0,
                "credited_hours": 0,
                "unmet_hours": 0,
                "carryover_status": "needs_review",
                "needs_review_reason": review_reason,
            }
            continue

        type_keys = set(targets)
        type_keys.update(
            training_type
            for year, training_type in records_by_year_type
            if year == service_year and training_type in {"동원훈련Ⅰ형", "동원훈련Ⅱ형", "기본훈련", "작계훈련"}
        )
        for training_type in sorted(type_keys):
            target = targets.get(training_type, 0)
            current_records = records_by_year_type.get((service_year, training_type), [])
            actual_counted = 0
            estimated_counted = 0
            credited = 0
            current_deferred_type = None
            for record in current_records:
                policy = policies.get(record.attendance_status)
                if policy is None:
                    review_reason = "unknown_attendance_status"
                    continue
                if policy["counts_hours"]:
                    if record.source_kind == "estimated":
                        estimated_counted += record.training_hours
                    else:
                        actual_counted += record.training_hours
                approved_holds = _approved_for_record(postponements, record, "hold")
                if approved_holds:
                    hold_credit = sum(
                        item.credited_hours if item.credited_hours is not None
                        else record.training_hours or target
                        for item in approved_holds
                    )
                    credited = min(target, credited + hold_credit)
                elif policy["credits_hours"]:
                    credited = min(target, credited + (record.training_hours or target))
                if (
                    TYPE1_DEFERRAL_CONVERTS_TO_TYPE2
                    and training_type == "동원훈련Ⅰ형"
                    and _approved_for_record(postponements, record, "delay")
                ):
                    current_deferred_type = "동원훈련Ⅱ형"

            available_by_record: list[tuple[Education, int]] = []
            for record in current_records:
                policy = policies.get(record.attendance_status)
                if policy and policy["counts_hours"] and record.training_hours > 0:
                    available_by_record.append((record, record.training_hours))
            owed_list = [debt for debt in pending_demands if debt.training_type == training_type and debt.remaining_hours > 0]
            owed_list.sort(key=lambda debt: (debt.origin_year, debt.origin_round))
            estimated_allocated = 0
            for record, hours in available_by_record:
                remaining_hours = hours
                for debt in owed_list:
                    if remaining_hours <= 0:
                        break
                    amount = min(debt.remaining_hours, remaining_hours)
                    debt.remaining_hours -= amount
                    remaining_hours -= amount
                    if record.source_kind == "estimated":
                        estimated_allocated += amount
                    allocations.append(_Allocation(
                        (debt.origin_year, debt.training_type, debt.origin_round), record.id, amount
                    ))
            estimated_to_current = max(0, estimated_counted - estimated_allocated)
            unmet = max(target - actual_counted - estimated_to_current - credited, 0)
            calendar_year = obligation_calendar_year(service_year, base_date, current_year, today)
            closed = obligation_year_is_closed(service_year, base_date, current_year, today)
            carry_status = "none"
            current_round = rounds.get((service_year, training_type), 1)
            if unmet and closed:
                matching_deferral = current_deferred_type is not None
                debt_type = current_deferred_type or training_type
                debt_round = max((
                    record.training_round for record in current_records
                    if record.attendance_status in UNEXCUSED_ABSENCE | {"연기", "postponed"}
                ), default=1)
                unconfirmed = any(record.attendance_status in {"scheduled", "훈련 예정", "overdue"} for record in current_records)
                debt = _Debt(
                    person_id=person_id,
                    origin_year=service_year,
                    training_type=debt_type,
                    origin_round=debt_round,
                    current_round=rounds.get((service_year, debt_type), 1),
                    original_hours=unmet,
                    remaining_hours=unmet,
                    status="unconfirmed" if unconfirmed else "open",
                    reason_code="approved_deferral" if matching_deferral else "prior_year_shortfall",
                    converted_from_type=training_type if matching_deferral else None,
                )
                debt_key = (debt.origin_year, debt.training_type, debt.origin_round)
                previous = debt_by_key.get(debt_key)
                if previous is not None:
                    previous.original_hours += unmet
                    previous.remaining_hours += unmet
                else:
                    debt_by_key[debt_key] = debt
                    pending_demands.append(debt)
                carry_status = "unconfirmed" if unconfirmed else "open"
            if review_reason:
                result_values[(service_year, "NEEDS_REVIEW")] = {
                    "required_hours": 0,
                    "counted_hours": 0,
                    "credited_hours": 0,
                    "unmet_hours": 0,
                    "carryover_status": "needs_review",
                    "needs_review_reason": review_reason,
                }
                break
            result_values[(service_year, training_type)] = {
                "required_hours": targets.get(training_type, 0),
                "counted_hours": actual_counted,
                "credited_hours": credited,
                "unmet_hours": unmet,
                "carryover_status": carry_status,
                "needs_review_reason": None,
            }
            if carry_status != "none":
                carried_count_by_year[service_year] = carried_count_by_year.get(service_year, 0) + unmet

        if service_year == current_year:
            transfer_hours = sum(
                record.training_hours
                for record in records
                if record.education_year == service_year
                and record.training_year == today.year
                and record.source_kind == "transfer"
                and policies.get(record.attendance_status, {}).get("counts_hours")
            )
            if transfer_hours >= 8:
                for (result_year, _), values in result_values.items():
                    if result_year == service_year:
                        values["unmet_hours"] = 0
                        values["carryover_status"] = "none"

    before = _derived_snapshot(db, person_id)
    existing_carryovers = {
        (row.origin_year, row.training_type, row.origin_round): row
        for row in db.scalars(select(TrainingCarryover).where(TrainingCarryover.person_id == person_id)).all()
    }
    debt_ids: dict[tuple[int, str, int], int] = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for key, debt in debt_by_key.items():
        row = existing_carryovers.get(key)
        if row is None:
            row = TrainingCarryover(
                person_id=person_id,
                origin_year=debt.origin_year,
                training_type=debt.training_type,
                origin_round=debt.origin_round,
                current_round=debt.current_round,
                original_hours=debt.original_hours,
                imported_hours=next((
                    item.imported_hours for item in imported_rows
                    if (item.origin_year, item.training_type, item.origin_round) == key
                ), 0),
                remaining_hours=debt.remaining_hours,
                status="resolved" if debt.remaining_hours == 0 else debt.status,
                reason_code=debt.reason_code,
                converted_from_type=debt.converted_from_type,
                updated_at=now,
            )
            db.add(row)
            db.flush()
        else:
            row.current_round = debt.current_round
            row.original_hours = debt.original_hours
            row.imported_hours = next((
                item.imported_hours for item in imported_rows
                if (item.origin_year, item.training_type, item.origin_round) == key
            ), row.imported_hours)
            row.remaining_hours = debt.remaining_hours
            row.status = "resolved" if debt.remaining_hours == 0 else debt.status
            row.reason_code = debt.reason_code
            row.converted_from_type = debt.converted_from_type
            row.updated_at = now
        debt_ids[key] = row.id

    for key, row in existing_carryovers.items():
        if key not in debt_by_key:
            if row.imported_hours > 0 and row.origin_year >= current_year:
                continue
            row.remaining_hours = 0
            row.status = "resolved"
            row.reason_code = "no_longer_required"
            row.updated_at = now

    db.execute(delete(TrainingCarryoverResolution).where(
        TrainingCarryoverResolution.carryover_id.in_(
            select(TrainingCarryover.id).where(TrainingCarryover.person_id == person_id)
        )
    ))
    for allocation in allocations:
        carryover_id = debt_ids.get(allocation.debt_key)
        if carryover_id is not None:
            db.add(TrainingCarryoverResolution(
                carryover_id=carryover_id,
                education_id=allocation.education_id,
                hours=allocation.hours,
            ))

    existing_results = {
        (row.service_year, row.training_type): row
        for row in db.scalars(select(TrainingYearResult).where(TrainingYearResult.person_id == person_id)).all()
    }
    for (service_year, training_type), values in result_values.items():
        row = existing_results.pop((service_year, training_type), None)
        if row is None:
            row = TrainingYearResult(
                person_id=person_id,
                service_year=service_year,
                training_type=training_type,
                **values,
                recalculated_at=now,
            )
            db.add(row)
        else:
            for name, value in values.items():
                setattr(row, name, value)
            row.recalculated_at = now
    for row in existing_results.values():
        db.delete(row)

    existing_rounds = {
        row.training_type: row
        for row in db.scalars(select(TrainingRoundState).where(TrainingRoundState.person_id == person_id)).all()
    }
    current_year_rounds = {
        training_type: current_round
        for (service_year, training_type), current_round in rounds.items()
        if service_year == current_year
    }
    for debt in debt_by_key.values():
        if debt.remaining_hours > 0 and debt.current_round >= 3:
            current_year_rounds[debt.training_type] = max(
                current_year_rounds.get(debt.training_type, 1), debt.current_round
            )
    for training_type, current_round in current_year_rounds.items():
        row = existing_rounds.pop(training_type, None)
        if row is None:
            db.add(TrainingRoundState(
                person_id=person_id,
                training_type=training_type,
                current_round=current_round,
                recalculated_at=now,
            ))
        else:
            row.current_round = current_round
            row.recalculated_at = now
    for row in existing_rounds.values():
        db.delete(row)

    db.flush()
    after = _derived_snapshot(db, person_id)
    actor_label = actor.strip()[:100] if isinstance(actor, str) and actor.strip() else "system"
    db.add(AuditLog(
        user_id=actor_user_id,
        action=f"training.recalculate.{reason}",
        table_name="person_training",
        entity_key=person_id,
        record_id=None,
        actor_label=actor_label,
        before_data=json.dumps(before, ensure_ascii=False, sort_keys=True),
        after_data=json.dumps(after, ensure_ascii=False, sort_keys=True),
        created_at=now,
    ))
    return {
        "person_id": person_id,
        "from_year": max(1, from_year),
        "through_year": current_year,
        "results": after["results"],
        "carryovers": after["carryovers"],
        "rounds": after["rounds"],
        "warnings": postponement_limit_warnings(db, person_id, today),
    }


def overlay_progress_with_recalculation(
    db: Session, person: Person, progress: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Project legacy risk metadata using the canonical per-type hour results."""
    results = db.scalars(select(TrainingYearResult).where(
        TrainingYearResult.person_id == person.military_number
    )).all()
    if not results:
        return progress
    by_year: dict[int, list[TrainingYearResult]] = {}
    for row in results:
        by_year.setdefault(row.service_year, []).append(row)
    carryovers = db.scalars(select(TrainingCarryover).where(
        TrainingCarryover.person_id == person.military_number,
        or_(
            TrainingCarryover.reason_code.is_(None),
            TrainingCarryover.reason_code != "no_longer_required",
        ),
    )).all()
    allocations = db.execute(
        select(TrainingCarryoverResolution.carryover_id, Education.education_year, TrainingCarryoverResolution.hours)
        .join(Education, Education.id == TrainingCarryoverResolution.education_id)
        .join(TrainingCarryover, TrainingCarryover.id == TrainingCarryoverResolution.carryover_id)
        .where(TrainingCarryover.person_id == person.military_number)
    ).all()
    allocated_before_year: dict[tuple[int, int], int] = {}
    for carryover_id, education_year, hours in allocations:
        for service_year in range(education_year, len(progress)):
            key = (carryover_id, service_year)
            allocated_before_year[key] = allocated_before_year.get(key, 0) + hours

    canonical: list[dict[str, object]] = []
    for item in progress:
        service_year = int(item["service_year"])
        year_results = by_year.get(service_year, [])
        review = next((row for row in year_results if row.needs_review_reason), None)
        if review is not None:
            canonical.append({
                **item,
                "training_plan": [],
                "target_hours": 0,
                "carryover_hours": 0,
                "required_hours": 0,
                "completed_hours": 0,
                "credited_hours": 0,
                "recognized_hours": 0,
                "unmet_required_hours": 0,
                "remaining_hours": 0,
                "over_limit": False,
                "completed": False,
                "training_status": "NEEDS_REVIEW",
                "needs_review_reason": review.needs_review_reason,
                "review_hints": list(item.get("review_hints", [])) + [review.needs_review_reason],
            })
            continue
        target = sum(row.required_hours for row in year_results)
        counted = sum(row.counted_hours for row in year_results)
        credited = sum(row.credited_hours for row in year_results)
        incoming = 0
        for row in carryovers:
            if row.origin_year >= service_year:
                continue
            already_resolved = allocated_before_year.get((row.id, service_year), 0)
            incoming += max(0, row.original_hours - already_resolved)
        required = target
        annual_remaining = max(required - counted - credited, 0)
        remaining = annual_remaining + incoming
        training_plan_rows = [
            {"name": row.training_type, "hours": row.required_hours}
            for row in year_results if row.required_hours > 0
        ]
        if service_year > (person.service_year or 0):
            training_status = "훈련 예정"
        elif required > 0 and remaining > 0:
            training_status = "훈련 미이수"
        elif required > 0:
            training_status = "훈련 이수"
        else:
            training_status = "훈련 대상 아님"
        canonical.append({
            **item,
            "training_plan": training_plan_rows,
            "target_hours": target,
            "carryover_hours": incoming,
            "required_hours": required,
            "completed_hours": counted,
            "credited_hours": credited,
            "recognized_hours": counted + credited,
            "unmet_required_hours": max(required - counted - credited, 0),
            "remaining_hours": remaining,
            "over_limit": counted + credited > required,
            "completed": remaining == 0,
            "training_status": training_status,
        })
    return canonical


def _derived_snapshot(db: Session, person_id: str) -> dict[str, object]:
    results = db.scalars(
        select(TrainingYearResult).where(TrainingYearResult.person_id == person_id)
        .order_by(TrainingYearResult.service_year, TrainingYearResult.training_type)
    ).all()
    carryovers = db.scalars(
        select(TrainingCarryover).where(TrainingCarryover.person_id == person_id)
        .order_by(TrainingCarryover.origin_year, TrainingCarryover.training_type, TrainingCarryover.origin_round)
    ).all()
    rounds = db.scalars(
        select(TrainingRoundState).where(TrainingRoundState.person_id == person_id)
        .order_by(TrainingRoundState.training_type)
    ).all()
    return {
        "results": [
            {
                "service_year": row.service_year,
                "training_type": row.training_type,
                "required_hours": row.required_hours,
                "counted_hours": row.counted_hours,
                "credited_hours": row.credited_hours,
                "unmet_hours": row.unmet_hours,
                "carryover_status": row.carryover_status,
                "needs_review_reason": row.needs_review_reason,
            }
            for row in results
        ],
        "carryovers": [
            {
                "origin_year": row.origin_year,
                "training_type": row.training_type,
                "origin_round": row.origin_round,
                "current_round": row.current_round,
                "original_hours": row.original_hours,
                "remaining_hours": row.remaining_hours,
                "status": row.status,
                "reason_code": row.reason_code,
                "converted_from_type": row.converted_from_type,
            }
            for row in carryovers
        ],
        "rounds": [
            {"training_type": row.training_type, "current_round": row.current_round}
            for row in rounds
        ],
    }


def recalculate_all_people(
    db: Session, reason: str = "manual", actor: str = "admin", today: date | None = None,
    actor_user_id: int | None = None,
) -> dict[str, object]:
    """Rebuild derived state for every person in the caller's transaction."""
    person_ids = db.scalars(select(Person.military_number).order_by(Person.military_number)).all()
    results = [
        recalculate_person(
            db, person_id, 1, reason, actor, today, actor_user_id=actor_user_id
        )
        for person_id in person_ids
    ]
    return {"people_recalculated": len(results), "results": results}


def run_jan1_rollover(db: Session, today: date | None = None) -> int:
    """Advance cached service years once on Jan 1 and rebuild each person's state."""
    if os.getenv("TRAINING_ROLLOVER_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return 0
    today = today or _today_korea()
    if today.month != 1 or today.day != 1:
        return 0
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    if db.get(TrainingRolloverRun, today.year) is not None:
        return 0

    people = db.scalars(select(Person).order_by(Person.military_number)).all()
    changed = 0
    for person in people:
        previous_year = person.service_year or 0
        base_date = _base_date(person)
        next_year = (
            service_year_for_date(base_date, today)
            if base_date is not None
            else previous_year + 1
        )
        if person.service_year != next_year:
            person.service_year = next_year
            changed += 1
        recalculate_person(
            db,
            person.military_number,
            max(1, previous_year),
            "rollover",
            "system: Jan 1 rollover",
            today,
        )
    db.add(TrainingRolloverRun(calendar_year=today.year))
    db.flush()
    return changed


def recalculate_ended_holds(db: Session, today: date | None = None) -> int:
    """Rebuild affected people once after each approved hold end date passes."""
    today = today or _today_korea()
    rows = db.scalars(select(Postponement).where(
        Postponement.status == "approved",
        Postponement.type.in_({"hold", "보류", "법규보류", "방침보류"}),
        Postponement.end_date.is_not(None),
        Postponement.end_date < today,
        Postponement.hold_ended_recalculated_at.is_(None),
    )).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    by_person: dict[str, list[Postponement]] = {}
    for row in rows:
        by_person.setdefault(row.person_id, []).append(row)
    for person_id, person_rows in by_person.items():
        recalculate_person(db, person_id, 1, "hold_ended", "system: hold expiration", today)
        for row in person_rows:
            row.hold_ended_recalculated_at = now
    db.flush()
    return len(rows)