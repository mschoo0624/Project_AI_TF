"""Schedule, roster, and result workflows for education training."""

from __future__ import annotations

from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.audit_log import AuditLog
from user.app.models.training_schedule import TrainingSchedule
from user.app.models.user import User
from user.app.schemas.training_results import (
    TrainingResultBatchConfirm,
    TrainingRosterAssignment,
    TrainingScheduleCreate,
    TrainingScheduleMove,
    TrainingScheduleRead,
    TrainingScheduleUpdate,
    TrainingScheduleVersion,
)
from user.app.services.auth import get_current_user, require_approver, require_scheduler, require_viewer
from user.app.services.training_results import (
    ResultBatchValidationError,
    assign_schedule_roster,
    cancel_schedule,
    complete_schedule,
    confirm_result_batch,
    create_schedule,
    delete_schedule,
    export_results_csv,
    enable_demo_early_save,
    person_result_history,
    result_worklists,
    schedule_assignment_targets,
    schedule_roster,
    move_schedule,
    update_schedule,
)

router = APIRouter(prefix="/reservists", tags=["training results"])


def require_roster_assigner(actor: User = Depends(get_current_user)) -> User:
    if actor.role not in {"scheduler", "approver"}:
        raise HTTPException(status_code=403, detail="Scheduler or approver role required")
    return actor


@router.get("/training-schedules", response_model=list[TrainingScheduleRead])
def list_training_schedules(
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_viewer),
) -> list[TrainingSchedule]:
    return db.scalars(select(TrainingSchedule).order_by(TrainingSchedule.id.desc())).all()


@router.post("/training-schedules", response_model=TrainingScheduleRead, status_code=201)
def add_training_schedule(
    payload: TrainingScheduleCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> TrainingSchedule:
    try:
        schedule = create_schedule(db, payload, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.post("/training-schedules/{schedule_id}/move", response_model=TrainingScheduleRead)
def move_training_schedule(
    schedule_id: int,
    payload: TrainingScheduleMove,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> TrainingSchedule:
    try:
        schedule = move_schedule(db, schedule_id, payload, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.put("/training-schedules/{schedule_id}", response_model=TrainingScheduleRead)
def edit_training_schedule(
    schedule_id: int,
    payload: TrainingScheduleUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> TrainingSchedule:
    try:
        schedule = update_schedule(db, schedule_id, payload, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.delete("/training-schedules/{schedule_id}", status_code=204)
def remove_training_schedule(
    schedule_id: int,
    payload: TrainingScheduleVersion,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> Response:
    try:
        delete_schedule(db, schedule_id, payload.expected_version, actor)
        db.commit()
        return Response(status_code=204)
    except Exception:
        db.rollback()
        raise


@router.post("/training-schedules/{schedule_id}/cancel", response_model=TrainingScheduleRead)
def cancel_training_schedule(
    schedule_id: int,
    payload: TrainingScheduleVersion,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> TrainingSchedule:
    try:
        schedule = cancel_schedule(db, schedule_id, payload.expected_version, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.post("/training-schedules/{schedule_id}/complete", response_model=TrainingScheduleRead)
def complete_training_schedule(
    schedule_id: int,
    payload: TrainingScheduleVersion,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> TrainingSchedule:
    try:
        schedule = complete_schedule(db, schedule_id, payload.expected_version, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.post("/training-schedules/{schedule_id}/enable-demo-early-save", response_model=TrainingScheduleRead)
def enable_demo_training_early_save(
    schedule_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> TrainingSchedule:
    try:
        schedule = enable_demo_early_save(db, schedule_id, actor)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception:
        db.rollback()
        raise


@router.post("/training-schedules/{schedule_id}/roster", status_code=201)
def assign_training_roster(
    schedule_id: int,
    payload: TrainingRosterAssignment,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roster_assigner),
) -> dict[str, object]:
    try:
        records = assign_schedule_roster(db, schedule_id, payload, actor)
        db.commit()
        return {
            "schedule_id": schedule_id,
            "assigned": [
                {"education_id": row.id, "military_number": row.person_id, "version": row.version}
                for row in records
            ],
        }
    except Exception:
        db.rollback()
        raise


@router.get("/training-schedules/{schedule_id}/roster")
def get_training_roster(
    schedule_id: int,
    session_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_viewer),
) -> dict[str, object]:
    return schedule_roster(db, schedule_id, session_id)


@router.get("/training-schedules/{schedule_id}/assignment-candidates")
def get_training_assignment_candidates(
    schedule_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> dict[str, object]:
    targets = schedule_assignment_targets(db, schedule_id, actor.role)
    return {
        "military_numbers": [
            target["military_number"]
            for target in targets if target["assignment_error"] is None
        ],
        "training_targets": targets,
    }


@router.post("/training-results/bulk-confirm")
def bulk_confirm_training_results(
    payload: TrainingResultBatchConfirm,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> dict[str, object]:
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        result = confirm_result_batch(db, payload, actor)
        db.commit()
        return result
    except ResultBatchValidationError as error:
        db.rollback()
        raise HTTPException(
            status_code=error.status_code,
            detail={"message": str(error), "errors": error.errors},
        ) from error
    except Exception:
        db.rollback()
        raise


@router.get("/training-results/worklists")
def get_training_result_worklists(
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_viewer),
) -> dict[str, list[dict[str, object]]]:
    return result_worklists(db)


@router.get("/training-results/people/{military_number}")
def get_person_training_result_history(
    military_number: str,
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_viewer),
) -> dict[str, object]:
    history = person_result_history(db, military_number)
    db.add(AuditLog(
        user_id=_viewer.id,
        action="training_result.history.view",
        table_name="person_training_history",
        entity_key=military_number,
        actor_label=_viewer.username,
    ))
    db.commit()
    return history


@router.get("/training-results/export.csv")
def download_training_results(
    service_year: int | None = Query(default=None, ge=1, le=99),
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> Response:
    content = export_results_csv(db, service_year)
    db.add(AuditLog(
        user_id=actor.id,
        action="training_results.export",
        table_name="training_results_export",
        entity_key=str(service_year) if service_year is not None else "all",
        actor_label=actor.username,
        after_data=json.dumps({"service_year": service_year}, sort_keys=True),
    ))
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="training-results-{date.today().isoformat()}.csv"'},
    )