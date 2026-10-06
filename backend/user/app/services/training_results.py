"""Schedule rosters and transactional training-result confirmation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.training_schedule import (
    TrainingNotification,
    TrainingResultBatch,
    TrainingSchedule,
    TrainingSession,
)
from user.app.models.user import User
from user.app.schemas.training_results import (
    TrainingResultBatchConfirm,
    TrainingScheduleCreate,
    TrainingScheduleUpdate,
    TrainingRosterAssignment,
)
from user.app.services.training import (
    ATTENDANCE_HOURS_REQUIRED,
    ATTENDANCE_ZERO_HOURS,
    EARLY_DISMISSAL_COUNTS_HOURS,
    ROUND_SCHEDULED,
    UNEXCUSED_ABSENCE,
    OVERDUE_GRACE_DAYS,
    all_training_progress,
    mobilization_status_for_year,
    training_record_required_hours,
    training_round_satisfied,
    training_round_sequence_error,
    training_plan_has_type,
)
from user.app.services.training_recalculation import recalculate_person

RESULT_GRACE_DAYS = OVERDUE_GRACE_DAYS
STATUS_ALIASES = {
    "이수": "이수",
    "completed": "이수",
    "참석": "참석",
    "attended": "참석",
    "무단불참": "무단불참",
    "무단_불참": "무단불참",
    "unexcused_absence": "무단불참",
    "연기": "연기",
    "postponed": "연기",
    "보류": "보류",
    "round_hold": "보류",
    "조기퇴소": "조기퇴소",
}
VALID_RESULT_STATES = {"이수", "참석", "무단불참", "연기", "보류", "조기퇴소"}
DELAY_TYPES = {"delay", "연기"}
HOLD_TYPES = {"hold", "보류", "법규보류", "방침보류"}


class ResultBatchValidationError(Exception):
    def __init__(self, errors: list[dict[str, Any]], status_code: int = 422):
        super().__init__("Training result batch validation failed")
        self.errors = errors
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def result_state_hours_error(attendance_status: str, training_hours: int) -> str | None:
    canonical = STATUS_ALIASES.get(attendance_status)
    if canonical not in VALID_RESULT_STATES:
        return "지원하지 않는 결과 상태입니다."
    counted = canonical in {"이수", "참석"} or (
        canonical == "조기퇴소" and EARLY_DISMISSAL_COUNTS_HOURS
    )
    if counted and training_hours <= 0:
        return "이수/참석 또는 시간 인정 조기퇴소는 양수 시간이 필요합니다."
    if not counted and training_hours != 0:
        return "해당 결과 상태는 훈련시간이 0이어야 합니다."
    return None


def _record_snapshot(record: Education) -> dict[str, Any]:
    return {
        "education_year": record.education_year,
        "training_year": record.training_year,
        "scheduled_date": record.scheduled_date.isoformat() if record.scheduled_date else None,
        "schedule_id": record.schedule_id,
        "training_type": record.training_type,
        "training_round": record.training_round,
        "attendance_status": record.attendance_status,
        "training_hours": record.training_hours,
        "source_kind": record.source_kind,
        "confirmed_by": record.confirmed_by,
        "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
        "notes": record.notes,
        "version": record.version,
    }


def _schedule_snapshot(schedule: TrainingSchedule) -> dict[str, Any]:
    return {
        "title": schedule.title,
        "training_type": schedule.training_type,
        "training_round": schedule.training_round,
        "service_year": schedule.service_year,
        "status": schedule.status,
        "demo_early_save_enabled": schedule.demo_early_save_enabled,
        "demo_early_save_used": schedule.demo_early_save_used,
        "version": schedule.version,
        "sessions": [
            {"day_number": item.day_number, "session_date": item.session_date.isoformat(),
             "credited_hours": item.credited_hours}
            for item in schedule.sessions
        ],
    }


def _validated_sessions(sessions) -> list:
    ordered = sorted(sessions, key=lambda item: item.day_number)
    day_numbers = [item.day_number for item in ordered]
    session_dates = [item.session_date for item in ordered]
    if len(day_numbers) != len(set(day_numbers)):
        raise HTTPException(status_code=422, detail="Session day numbers must be unique")
    if len(session_dates) != len(set(session_dates)):
        raise HTTPException(status_code=422, detail="Session dates must be unique")
    if day_numbers != list(range(1, len(ordered) + 1)):
        raise HTTPException(status_code=422, detail="Session days must be numbered consecutively from 1")
    if session_dates != sorted(session_dates):
        raise HTTPException(status_code=422, detail="Session dates must be in chronological order")
    if len({item.session_date.year for item in ordered}) != 1:
        raise HTTPException(status_code=422, detail="A training event must stay within one calendar year")
    if any(item.session_date < date.today() for item in ordered):
        raise HTTPException(status_code=422, detail="Sessions cannot be moved into the past")
    return ordered


def _required_round_hours(db: Session, person: Person, record: Education) -> int | None:
    return training_record_required_hours(
        record.training_type,
        record.education_year,
        mobilization_status_for_year(db, person, record.education_year),
        person.branch,
        person.rank,
        person.position,
    )


def _linked_approved_postponement(db: Session, record: Education, expected_types: set[str]) -> bool:
    return bool(db.scalar(select(Postponement.id).where(
        Postponement.education_record_id == record.id,
        Postponement.person_id == record.person_id,
        Postponement.status == "approved",
        Postponement.type.in_(expected_types),
    ).limit(1)))


def create_schedule(
    db: Session, payload: TrainingScheduleCreate, actor: User
) -> TrainingSchedule:
    sessions = _validated_sessions(payload.sessions)

    schedule = TrainingSchedule(
        title=payload.title.strip(),
        training_type=payload.training_type.strip(),
        training_round=payload.training_round,
        service_year=payload.service_year,
        created_by_user_id=actor.id,
        sessions=[TrainingSession(
            day_number=item.day_number,
            session_date=item.session_date,
            credited_hours=item.credited_hours,
        ) for item in sessions],
    )
    db.add(schedule)
    db.flush()
    db.add(AuditLog(
        action="training_schedule.create",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
        created_at=_now(),
    ))
    return schedule


def enable_demo_early_save(
    db: Session, schedule_id: int, actor: User
) -> TrainingSchedule:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    if schedule.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled demo events can use early result entry")
    if schedule.demo_early_save_enabled or schedule.demo_early_save_used:
        raise HTTPException(status_code=409, detail="The demo early-save allowance is already enabled or used")
    if not any(marker in schedule.title.casefold() for marker in ("demo", "test", "데모", "샘플")):
        raise HTTPException(status_code=422, detail="Only a clearly labeled demo schedule can use early result entry")

    records = db.scalars(select(Education).where(Education.schedule_id == schedule_id)).all()
    if not records or any(not record.person_id.startswith("26-TEST-") for record in records):
        raise HTTPException(status_code=422, detail="Early result entry requires a roster made only of 26-TEST people")
    last_session = max((item.session_date for item in schedule.sessions), default=None)
    if last_session is None or last_session < date.today():
        raise HTTPException(status_code=409, detail="Early result entry is only for an upcoming demo event")

    before = _schedule_snapshot(schedule)
    schedule.demo_early_save_enabled = True
    schedule.version += 1
    db.flush()
    db.add(AuditLog(
        action="training_schedule.demo_early_save.enable",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        before_data=json.dumps(before, ensure_ascii=False),
        after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
        created_at=_now(),
    ))
    return schedule


def move_schedule(
    db: Session, schedule_id: int, payload: TrainingScheduleMove, actor: User
) -> TrainingSchedule:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    _advance_schedule_version(db, schedule, payload.expected_version)
    if schedule.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled events can be moved")
    records = db.scalars(select(Education).where(Education.schedule_id == schedule_id)).all()
    if any(record.attendance_status not in ROUND_SCHEDULED or record.confirmed_by for record in records):
        raise HTTPException(status_code=409, detail="Events with confirmed results cannot be moved")

    sessions = _validated_sessions(payload.sessions)
    before = _schedule_snapshot(schedule)
    schedule.sessions.clear()
    db.flush()
    schedule.sessions.extend(TrainingSession(
        day_number=item.day_number,
        session_date=item.session_date,
        credited_hours=item.credited_hours,
    ) for item in sessions)
    first_session_date = sessions[0].session_date
    for record in records:
        record.scheduled_date = first_session_date
        record.training_year = first_session_date.year
    db.flush()
    db.add(AuditLog(
        action="training_schedule.move",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        before_data=json.dumps(before, ensure_ascii=False),
        after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
        created_at=_now(),
    ))
    return schedule


def update_schedule(
    db: Session, schedule_id: int, payload: TrainingScheduleUpdate, actor: User
) -> TrainingSchedule:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    _advance_schedule_version(db, schedule, payload.expected_version)
    if schedule.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled events can be edited")
    if schedule.demo_early_save_enabled or schedule.demo_early_save_used:
        raise HTTPException(status_code=409, detail="Demo early-save schedules cannot be edited")
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="Schedule title cannot be empty")

    records = db.scalars(select(Education).where(Education.schedule_id == schedule_id)).all()
    if any(record.attendance_status not in ROUND_SCHEDULED or record.confirmed_by for record in records):
        raise HTTPException(status_code=409, detail="Events with confirmed results cannot be edited")
    identity_changed = (
        schedule.training_type != payload.training_type.strip()
        or schedule.training_round != payload.training_round
        or schedule.service_year != payload.service_year
    )
    if records and identity_changed:
        raise HTTPException(
            status_code=409,
            detail="Training type, year, and round cannot change after people are assigned",
        )

    sessions = _validated_sessions(payload.sessions)
    before = _schedule_snapshot(schedule)
    schedule.title = payload.title.strip()
    schedule.training_type = payload.training_type.strip()
    schedule.training_round = payload.training_round
    schedule.service_year = payload.service_year
    schedule.sessions.clear()
    db.flush()
    schedule.sessions.extend(TrainingSession(
        day_number=item.day_number,
        session_date=item.session_date,
        credited_hours=item.credited_hours,
    ) for item in sessions)
    first_session_date = sessions[0].session_date
    for record in records:
        record.scheduled_date = first_session_date
        record.training_year = first_session_date.year
    db.flush()
    db.add(AuditLog(
        action="training_schedule.update",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        before_data=json.dumps(before, ensure_ascii=False),
        after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
        created_at=_now(),
    ))
    return schedule


def cancel_schedule(
    db: Session, schedule_id: int, expected_version: int, actor: User
) -> TrainingSchedule:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    _advance_schedule_version(db, schedule, expected_version)
    if schedule.status != "scheduled":
        raise HTTPException(status_code=409, detail="Only scheduled events can be cancelled")
    records = db.scalars(select(Education).where(Education.schedule_id == schedule_id)).all()
    if any(record.attendance_status not in ROUND_SCHEDULED or record.confirmed_by for record in records):
        raise HTTPException(status_code=409, detail="Events with confirmed results cannot be cancelled")

    before = _schedule_snapshot(schedule)
    schedule.status = "cancelled"
    for record in records:
        notification = db.get(TrainingNotification, record.id)
        if notification is not None:
            notification.status = "cancelled"
            notification.updated_at = _now()
    db.add(AuditLog(
        action="training_schedule.cancel",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        before_data=json.dumps(before, ensure_ascii=False),
        after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
        created_at=_now(),
    ))
    return schedule


def delete_schedule(
    db: Session, schedule_id: int, expected_version: int, actor: User
) -> None:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    _advance_schedule_version(db, schedule, expected_version)
    if schedule.demo_early_save_enabled or schedule.demo_early_save_used:
        raise HTTPException(status_code=409, detail="Demo early-save schedules cannot be deleted")
    if db.scalar(select(Education.id).where(Education.schedule_id == schedule_id).limit(1)) is not None:
        raise HTTPException(
            status_code=409,
            detail="Schedules with assigned people cannot be deleted; cancel the schedule instead",
        )

    before = _schedule_snapshot(schedule)
    db.add(AuditLog(
        action="training_schedule.delete",
        table_name="training_schedule",
        record_id=schedule.id,
        user_id=actor.id,
        actor_label=actor.username,
        before_data=json.dumps(before, ensure_ascii=False),
        created_at=_now(),
    ))
    db.delete(schedule)
    db.flush()


def _advance_schedule_version(
    db: Session, schedule: TrainingSchedule, expected_version: int
) -> None:
    result = db.execute(
        update(TrainingSchedule)
        .where(
            TrainingSchedule.id == schedule.id,
            TrainingSchedule.version == expected_version,
        )
        .values(version=TrainingSchedule.version + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Training schedule was changed by another user")
    db.refresh(schedule, attribute_names=["version"])


def assign_schedule_roster(
    db: Session, schedule_id: int, payload: TrainingRosterAssignment, actor: User
) -> list[Education]:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    if schedule.status != "scheduled":
        raise HTTPException(status_code=409, detail="Roster can only be changed for scheduled events")
    if schedule.demo_early_save_enabled or schedule.demo_early_save_used:
        raise HTTPException(status_code=409, detail="The roster is locked for this demo result entry")
    if len(payload.person_ids) != len(set(payload.person_ids)):
        raise HTTPException(status_code=422, detail="Roster contains duplicate military numbers")

    people = {
        person.military_number: person
        for person in db.scalars(select(Person).where(Person.military_number.in_(payload.person_ids))).all()
    }
    errors: list[dict[str, str]] = []
    first_session = schedule.sessions[0] if schedule.sessions else None
    if first_session is None:
        raise HTTPException(status_code=409, detail="Schedule has no sessions")

    records: list[Education] = []
    for person_id in payload.person_ids:
        person = people.get(person_id)
        if person is None:
            errors.append({"person_id": person_id, "error": "Reservist not found"})
            continue
        if person.service_year is not None and schedule.service_year > person.service_year:
            errors.append({"person_id": person_id, "error": "Service year is in the future"})
            continue
        if db.scalar(select(Education.id).where(
            Education.person_id == person_id,
            Education.schedule_id == schedule_id,
        ).limit(1)) is not None:
            errors.append({"person_id": person_id, "error": "Person is already on this roster"})
            continue

        year_records = db.scalars(select(Education).where(
            Education.person_id == person_id,
            Education.education_year == schedule.service_year,
        )).all()
        progress = all_training_progress(db, person)
        if schedule.service_year >= len(progress):
            errors.append({"person_id": person_id, "error": "Service year has no training plan"})
            continue
        year_progress = progress[schedule.service_year]
        if int(year_progress["required_hours"]) <= 0:
            errors.append({"person_id": person_id, "error": "Service year has no training requirement"})
            continue
        required_hours = training_record_required_hours(
            schedule.training_type,
            schedule.service_year,
            mobilization_status_for_year(db, person, schedule.service_year),
            person.branch,
            person.rank,
            person.position,
            bool(year_progress.get("officer_type_ii_makeup")),
        )
        approved_deferral_ids = {
            record_id for record_id in db.scalars(select(Postponement.education_record_id).where(
                Postponement.person_id == person_id,
                Postponement.status == "approved",
                Postponement.type.in_(DELAY_TYPES),
                Postponement.education_record_id.is_not(None),
            )).all() if record_id is not None
        }
        sequence_error = training_round_sequence_error(
            year_records,
            schedule.training_type,
            schedule.training_round,
            "scheduled",
            0,
            required_hours,
            approved_deferral_record_ids=approved_deferral_ids,
        )
        if sequence_error:
            errors.append({"person_id": person_id, "error": sequence_error})
            continue
        records.append(Education(
            person_id=person_id,
            education_year=schedule.service_year,
            training_year=first_session.session_date.year,
            scheduled_date=first_session.session_date,
            schedule_id=schedule.id,
            training_type=schedule.training_type,
            training_round=schedule.training_round,
            attendance_status="scheduled",
            training_hours=0,
            source_kind="manual",
        ))

    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    db.add_all(records)
    db.flush()
    for record in records:
        db.add(TrainingNotification(education_id=record.id, status="pending"))
        db.add(AuditLog(
            action="training_schedule.assign",
            table_name="education",
            record_id=record.id,
            user_id=actor.id,
            actor_label=actor.username,
            after_data=json.dumps(_record_snapshot(record), ensure_ascii=False),
            created_at=_now(),
        ))
    return records


def schedule_assignment_candidates(db: Session, schedule_id: int) -> list[str]:
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    if (
        schedule.status != "scheduled"
        or schedule.demo_early_save_enabled
        or schedule.demo_early_save_used
        or not schedule.sessions
    ):
        return []

    assigned_ids = set(db.scalars(
        select(Education.person_id).where(Education.schedule_id == schedule_id)
    ).all())
    people = db.scalars(
        select(Person)
        .where(Person.service_year == schedule.service_year)
        .order_by(Person.name, Person.military_number)
    ).all()
    return [
        person.military_number
        for person in people
        if person.military_number not in assigned_ids
        and training_plan_has_type(
            schedule.training_type,
            schedule.service_year,
            mobilization_status_for_year(db, person, schedule.service_year),
            person.branch,
            person.rank,
            person.position,
        )
    ]


def schedule_roster(
    db: Session, schedule_id: int, session_id: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    schedule = db.get(TrainingSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Training schedule not found")
    if session_id is not None and all(item.id != session_id for item in schedule.sessions):
        raise HTTPException(status_code=404, detail="Session does not belong to this schedule")
    last_day = max((item.session_date for item in schedule.sessions), default=None)
    due_date = last_day + timedelta(days=RESULT_GRACE_DAYS) if last_day else None
    missing_due = due_date is not None and today > due_date
    rows = db.scalars(select(Education).where(
        Education.schedule_id == schedule_id,
    ).order_by(Education.person_id)).all()
    results = []
    counts = {"attended": 0, "completed": 0, "absent": 0, "missing": 0, "deferred": 0}
    for record in rows:
        person = db.get(Person, record.person_id)
        status_value = record.attendance_status
        displayed_status = "결과 미입력" if status_value in ROUND_SCHEDULED and missing_due else status_value
        is_completed = training_round_satisfied(
            status_value, record.training_hours,
            _required_round_hours(db, person, record) if person else None,
        )
        if status_value in {"참석", "attended"}:
            counts["attended"] += 1
        if is_completed:
            counts["completed"] += 1
        if status_value in UNEXCUSED_ABSENCE:
            counts["absent"] += 1
        if displayed_status == "결과 미입력":
            counts["missing"] += 1
        if status_value in {"연기", "postponed", "보류", "round_hold"}:
            counts["deferred"] += 1
        notification = db.get(TrainingNotification, record.id)
        results.append({
            "education_id": record.id,
            "version": record.version,
            "military_number": record.person_id,
            "name": person.name if person else "",
            "training_type": record.training_type,
            "training_round": record.training_round,
            "attendance_status": status_value,
            "result_status": displayed_status,
            "training_hours": record.training_hours,
            "required_hours": _required_round_hours(db, person, record) if person else None,
            "confirmed_by": record.confirmed_by,
            "notes": record.notes,
            "source_kind": record.source_kind,
            "schedule_id": record.schedule_id,
            "notification": {
                "status": notification.status,
                "issued_at": notification.issued_at,
                "last_attempt_at": notification.last_attempt_at,
                "retries": notification.retries,
            } if notification else None,
        })
    return {
        "schedule": {
            "id": schedule.id,
            "title": schedule.title,
            "training_type": schedule.training_type,
            "training_round": schedule.training_round,
            "service_year": schedule.service_year,
            "status": schedule.status,
            "last_session_date": last_day,
            "result_due_date": due_date,
            "sessions": [
                {"id": item.id, "day_number": item.day_number,
                 "session_date": item.session_date, "credited_hours": item.credited_hours}
                for item in schedule.sessions
            ],
        },
        "selected_session_id": session_id,
        "counts": counts,
        "roster": results,
    }


def result_worklists(db: Session, today: date | None = None) -> dict[str, list[dict[str, Any]]]:
    today = today or date.today()
    records = db.scalars(select(Education).where(or_(
        Education.schedule_id.is_not(None),
        Education.attendance_status.in_(UNEXCUSED_ABSENCE),
    ))).all()
    missing: list[dict[str, Any]] = []
    scheduler_confirmable: list[dict[str, Any]] = []
    approver_required: list[dict[str, Any]] = []
    for record in records:
        schedule = db.get(TrainingSchedule, record.schedule_id)
        person = db.get(Person, record.person_id)
        if schedule is None and record.schedule_id is not None:
            continue
        if schedule is not None and schedule.status != "scheduled":
            continue
        base = {
            "education_id": record.id,
            "version": record.version,
            "military_number": record.person_id,
            "name": person.name if person else "",
            "schedule_id": schedule.id if schedule else None,
            "schedule_title": schedule.title if schedule else "기존 훈련 기록",
            "training_type": record.training_type,
            "training_round": record.training_round,
            "attendance_status": record.attendance_status,
        }
        last_day = max((item.session_date for item in schedule.sessions), default=None) if schedule else record.scheduled_date
        if (
            record.attendance_status in ROUND_SCHEDULED
            and last_day is not None
            and today > last_day + timedelta(days=RESULT_GRACE_DAYS)
        ):
            missing.append({**base, "result_status": "결과 미입력", "last_session_date": last_day})
        if record.attendance_status in UNEXCUSED_ABSENCE and not record.confirmed_by:
            target = approver_required if (
                record.training_round >= 3
                or record.training_type in {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"}
            ) else scheduler_confirmable
            target.append(base)
    late_deferral_review: list[dict[str, Any]] = []
    records_by_id = {record.id: record for record in records}
    audit_rows = db.scalars(select(AuditLog).where(
        AuditLog.table_name == "education",
        AuditLog.action == "training_result.bulk_confirm",
        AuditLog.record_id.is_not(None),
    ).order_by(AuditLog.created_at.desc())).all()
    for audit in audit_rows:
        record = records_by_id.get(audit.record_id or -1)
        if record is None or record.attendance_status not in {"연기", "보류"}:
            continue
        try:
            before = json.loads(audit.before_data or "{}")
            after = json.loads(audit.after_data or "{}")
        except json.JSONDecodeError:
            continue
        if before.get("attendance_status") not in UNEXCUSED_ABSENCE or after.get("attendance_status") not in {"연기", "보류"}:
            continue
        person = db.get(Person, record.person_id)
        schedule = db.get(TrainingSchedule, record.schedule_id) if record.schedule_id else None
        late_deferral_review.append({
            "education_id": record.id,
            "military_number": record.person_id,
            "name": person.name if person else "",
            "schedule_title": schedule.title if schedule else "기존 훈련 기록",
            "approved_state": record.attendance_status,
            "actor": audit.actor_label,
            "created_at": audit.created_at.isoformat(),
        })
    return {
        "missing_results": missing,
        "import_review": [],
        "absences_scheduler_can_confirm": scheduler_confirmable,
        "absences_needing_approver": approver_required,
        "late_deferral_review": late_deferral_review,
    }


def person_result_history(db: Session, military_number: str) -> dict[str, Any]:
    person = db.get(Person, military_number)
    if person is None:
        raise HTTPException(status_code=404, detail="Reservist not found")
    progress = all_training_progress(db, person)
    records = db.scalars(select(Education).where(
        Education.person_id == military_number,
    ).order_by(Education.education_year, Education.training_year, Education.training_round, Education.id)).all()
    record_ids = [record.id for record in records]
    audits = db.scalars(select(AuditLog).where(
        AuditLog.table_name == "education",
        AuditLog.record_id.in_(record_ids) if record_ids else AuditLog.record_id.is_(None),
    ).order_by(AuditLog.created_at.desc())).all()
    audit_by_record: dict[int, list[dict[str, Any]]] = {}
    for audit in audits:
        if audit.record_id is None:
            continue
        audit_by_record.setdefault(audit.record_id, []).append({
            "action": audit.action,
            "user_id": audit.user_id,
            "actor": audit.actor_label,
            "created_at": audit.created_at.isoformat(),
            "before": json.loads(audit.before_data) if audit.before_data else None,
            "after": json.loads(audit.after_data) if audit.after_data else None,
        })
    return {
        "military_number": military_number,
        "name": person.name,
        "years": [
            {
                "service_year": item["service_year"],
                "required_hours": item["required_hours"],
                "counted_hours": item["completed_hours"],
                "remaining_hours": item["remaining_hours"],
                "prosecution_status": item["prosecution_status"],
            }
            for item in progress if int(item["service_year"]) > 0
        ],
        "records": [
            {
                "education_id": record.id,
                "service_year": record.education_year,
                "training_year": record.training_year,
                "schedule_id": record.schedule_id,
                "training_type": record.training_type,
                "training_round": record.training_round,
                "attendance_status": record.attendance_status,
                "training_hours": record.training_hours,
                "counted_hours": record.training_hours if (
                    record.attendance_status in ATTENDANCE_HOURS_REQUIRED
                    and record.source_kind != "estimated"
                ) else 0,
                "source_kind": record.source_kind,
                "version": record.version,
                "audit": audit_by_record.get(record.id, []),
            }
            for record in records
        ],
    }


def _entry_errors(
    db: Session,
    record: Education,
    person: Person,
    entry,
    actor: User,
    today: date,
) -> list[str]:
    errors: list[str] = []
    early_demo_save_enabled = False
    canonical = STATUS_ALIASES.get(entry.attendance_status)
    if canonical not in VALID_RESULT_STATES:
        return ["지원하지 않는 결과 상태입니다."]
    entry.attendance_status = canonical
    state_hours_error = result_state_hours_error(canonical, entry.training_hours)
    if state_hours_error:
        errors.append(state_hours_error)
    counted = canonical in {"이수", "참석"} or (
        canonical == "조기퇴소" and EARLY_DISMISSAL_COUNTS_HOURS
    )
    if canonical in {"연기", "보류"}:
        linked_type = DELAY_TYPES if canonical == "연기" else HOLD_TYPES
        if not _linked_approved_postponement(db, record, linked_type):
            errors.append("승인된 연기/보류 기록이 Education 기록에 연결되어야 합니다.")

    last_session = record.scheduled_date
    event_capacity: int | None = None
    if record.schedule_id is not None:
        schedule = db.get(TrainingSchedule, record.schedule_id)
        if schedule is None:
            errors.append("연결된 훈련 일정이 없습니다.")
        elif schedule.status != "scheduled":
            errors.append("취소되거나 종료된 일정에는 결과를 저장할 수 없습니다.")
        else:
            early_demo_save_enabled = schedule.demo_early_save_enabled
            sessions = schedule.sessions
            if not sessions:
                errors.append("일정에 세션 날짜가 없습니다.")
            else:
                last_session = max(item.session_date for item in sessions)
                event_capacity = sum(item.credited_hours for item in sessions)
    if last_session is None:
        errors.append("결과에 연결된 훈련일이 없습니다.")
    elif last_session >= today and not early_demo_save_enabled:
        errors.append("훈련 종료일 이후에만 결과를 저장할 수 있습니다.")
    if event_capacity is not None and entry.training_hours > event_capacity:
        errors.append(f"입력 시간이 일정 인정시간({event_capacity})을 초과합니다.")

    if record.attendance_status in UNEXCUSED_ABSENCE and canonical not in UNEXCUSED_ABSENCE:
        if not (entry.reversal_reason and entry.reversal_reason.strip()):
            errors.append("확정된 무단불참을 정정하려면 사유가 필요합니다.")

    if canonical == "무단불참":
        needs_approver = (
            record.training_round >= 3
            or record.training_type in {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"}
        )
        if needs_approver and actor.role != "approver":
            errors.append("3차 또는 동원훈련Ⅰ형 무단불참은 approver 확인이 필요합니다.")
    elif record.attendance_status in UNEXCUSED_ABSENCE and record.confirmed_by and actor.role != "approver":
        errors.append("확정된 무단불참의 취소/정정은 approver 권한이 필요합니다.")

    if counted:
        progress = all_training_progress(db, person)
        if record.education_year >= len(progress):
            errors.append("해당 복무연도의 훈련 부과 정보를 찾을 수 없습니다.")
        else:
            required_annual = int(progress[record.education_year]["required_hours"])
            current_counted = (
                record.training_hours
                if record.attendance_status in ATTENDANCE_HOURS_REQUIRED
                and record.source_kind != "estimated"
                else 0
            )
            other_hours = max(int(progress[record.education_year]["completed_hours"]) - current_counted, 0)
            remaining = max(required_annual - other_hours, 0)
            if entry.training_hours > remaining:
                if not entry.override_allowance:
                    errors.append(
                        f"연간 잔여 허용시간({remaining})을 초과합니다. 사유를 입력하고 초과 허용을 선택하세요."
                    )
                elif actor.role != "approver":
                    errors.append("연간 허용시간 초과 확인은 approver 권한이 필요합니다.")
                elif not (entry.override_reason and entry.override_reason.strip()):
                    errors.append("허용시간 초과 사유가 필요합니다.")
    elif entry.override_allowance or entry.override_reason:
        errors.append("초과 허용은 인정시간 결과에서만 사용할 수 있습니다.")
    return errors


def confirm_result_batch(
    db: Session, payload: TrainingResultBatchConfirm, actor: User,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    if payload.source_kind not in {"manual", "기록 초안"}:
        raise HTTPException(status_code=422, detail="Result source must be manual or 기록 초안")
    entry_ids = [entry.education_id for entry in payload.entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise ResultBatchValidationError([
            {"education_id": entry_id, "errors": ["한 묶음에 같은 기록이 두 번 있습니다."]}
            for entry_id in sorted({value for value in entry_ids if entry_ids.count(value) > 1})
        ])

    normalized_request = payload.model_dump(mode="json", exclude={"idempotency_key"})
    normalized_request["entries"] = sorted(normalized_request["entries"], key=lambda row: row["education_id"])
    request_hash = hashlib.sha256(
        json.dumps(normalized_request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    prior_batch = db.get(TrainingResultBatch, payload.idempotency_key)
    if prior_batch is not None:
        if prior_batch.user_id != actor.id or prior_batch.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency key was used for a different request")
        cached = json.loads(prior_batch.response_data)
        cached["replayed"] = True
        return cached

    records = {
        record.id: record
        for record in db.scalars(select(Education).where(Education.id.in_(entry_ids))).all()
    }
    people = {
        person.military_number: person
        for person in db.scalars(select(Person).where(
            Person.military_number.in_({record.person_id for record in records.values()})
        )).all()
    }
    errors: list[dict[str, Any]] = []
    stale = False
    early_demo_schedules_to_consume: set[int] = set()
    for entry in payload.entries:
        record = records.get(entry.education_id)
        row_errors: list[str] = []
        if record is None:
            row_errors.append("훈련 기록을 찾을 수 없습니다.")
        else:
            person = people.get(record.person_id)
            if person is None:
                row_errors.append("예비군 정보를 찾을 수 없습니다.")
            if record.version != entry.expected_version:
                stale = True
                row_errors.append("기록이 변경되었습니다. 새로고침 후 다시 편집하세요.")
            if person is not None:
                row_errors.extend(_entry_errors(db, record, person, entry, actor, today))
            if record.schedule_id is not None:
                schedule = db.get(TrainingSchedule, record.schedule_id)
                last_session = max((item.session_date for item in schedule.sessions), default=None) if schedule else None
                if (schedule is not None and schedule.demo_early_save_enabled
                        and last_session is not None and last_session >= today):
                    early_demo_schedules_to_consume.add(schedule.id)
        if row_errors:
            errors.append({"education_id": entry.education_id, "errors": row_errors})
    if errors:
        permission_error = any(
            "approver" in message.lower()
            for row in errors for message in row["errors"]
        )
        raise ResultBatchValidationError(errors, 409 if stale else 403 if permission_error else 422)

    for schedule_id in early_demo_schedules_to_consume:
        schedule = db.get(TrainingSchedule, schedule_id)
        if schedule is None or not schedule.demo_early_save_enabled:
            raise HTTPException(status_code=409, detail="The demo early-save allowance changed; reload and try again")
        before = _schedule_snapshot(schedule)
        schedule.demo_early_save_enabled = False
        schedule.demo_early_save_used = True
        schedule.version += 1
        db.flush()
        db.add(AuditLog(
            action="training_schedule.demo_early_save.consume",
            table_name="training_schedule",
            record_id=schedule.id,
            user_id=actor.id,
            actor_label=actor.username,
            before_data=json.dumps(before, ensure_ascii=False),
            after_data=json.dumps(_schedule_snapshot(schedule), ensure_ascii=False),
            created_at=_now(),
        ))

    updated: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    changed_people: dict[str, int] = {}
    for entry in payload.entries:
        record = records[entry.education_id]
        canonical = STATUS_ALIASES[entry.attendance_status]
        before = _record_snapshot(record)
        values = {
            "attendance_status": canonical,
            "training_hours": entry.training_hours,
            "notes": entry.notes,
            "source_kind": payload.source_kind,
            "confirmed_by": actor.username if canonical == "무단불참" else None,
            "confirmed_at": _now() if canonical == "무단불참" else None,
            "version": record.version + 1,
        }
        result = db.execute(
            update(Education)
            .where(Education.id == record.id, Education.version == entry.expected_version)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ResultBatchValidationError([{
                "education_id": record.id,
                "errors": ["기록이 동시에 변경되었습니다. 묶음 전체를 저장하지 않았습니다."],
            }], 409)
        db.expire(record)
        db.refresh(record)
        after = _record_snapshot(record)
        db.add(AuditLog(
            action="training_result.bulk_confirm",
            table_name="education",
            record_id=record.id,
            user_id=actor.id,
            actor_label=actor.username,
            before_data=json.dumps(before, ensure_ascii=False, sort_keys=True),
            after_data=json.dumps({
                **after,
                "override_reason": entry.override_reason,
                "reversal_reason": entry.reversal_reason,
            },
                                  ensure_ascii=False, sort_keys=True),
            created_at=_now(),
        ))
        changed_people[record.person_id] = min(
            changed_people.get(record.person_id, record.education_year), record.education_year
        )
        if entry.override_allowance:
            warnings.append({
                "education_id": record.id,
                "warning": "hours_exceed_remaining_allowance",
                "override_reason": entry.override_reason.strip() if entry.override_reason else "",
            })
        updated.append({
            "education_id": record.id,
            "version": record.version,
            "attendance_status": record.attendance_status,
            "training_hours": record.training_hours,
            "source_kind": record.source_kind,
        })

    for person_id, from_year in changed_people.items():
        recalculate_person(
            db, person_id, from_year, "training_result_bulk_confirmed", actor.username
        )
    db.flush()
    response = {
        "updated": updated,
        "warnings": warnings,
        "replayed": False,
        "recalculated_people": sorted(changed_people),
    }
    db.add(TrainingResultBatch(
        idempotency_key=payload.idempotency_key,
        user_id=actor.id,
        request_hash=request_hash,
        response_data=json.dumps(response, ensure_ascii=False, sort_keys=True),
        created_at=_now(),
    ))
    db.flush()
    return response


def export_results_csv(db: Session, service_year: int | None = None) -> str:
    query = select(Education).where(Education.schedule_id.is_not(None)).order_by(
        Education.education_year, Education.training_year, Education.id
    )
    if service_year is not None:
        query = query.where(Education.education_year == service_year)
    records = db.scalars(query).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "military_number", "name", "service_year", "training_year", "schedule_id",
        "training_type", "training_round", "scheduled_date", "attendance_status",
        "training_hours", "source_kind", "confirmed_by", "notes",
    ])

    def safe_cell(value: object) -> object:
        if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in {"=", "+", "-", "@"}:
            return f"'{value}"
        return value

    for record in records:
        person = db.get(Person, record.person_id)
        writer.writerow([safe_cell(value) for value in [
            record.person_id, person.name if person else "", record.education_year,
            record.training_year or "", record.schedule_id or "", record.training_type,
            record.training_round, record.scheduled_date.isoformat() if record.scheduled_date else "",
            record.attendance_status, record.training_hours, record.source_kind,
            record.confirmed_by or "", record.notes or "",
        ]])
    return output.getvalue()
