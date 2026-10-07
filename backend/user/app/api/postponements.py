"""Postponement API backed by the separate classifier service."""

from datetime import date, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.user import User
from user.app.schemas.postponement import PostponementCreate, PostponementRead, PostponementUpdate
from user.app.services.classifier_client import classify_reason, decide_submission
from user.app.services.auth import require_approver, require_scheduler, require_viewer
from user.app.services.training_recalculation import (
    HOLD_RESOLUTION_GRACE_DAYS,
    recalculate_person,
)


router = APIRouter(prefix="/postponements", tags=["postponements"])


def _actor_value(actor: User) -> str:
    return actor.username[:100]


@router.get("", response_model=list[PostponementRead])
def list_postponements(
    db: Session = Depends(get_db),
    _viewer: User = Depends(require_viewer),
) -> list[Postponement]:
    return list(db.scalars(select(Postponement).order_by(Postponement.id.desc())).all())


@router.post("", response_model=PostponementRead, status_code=status.HTTP_201_CREATED)
def create_postponement(
    payload: PostponementCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> Postponement:
    if db.get(Person, payload.person_id) is None:
        raise HTTPException(status_code=404, detail="Reservist not found")

    try:
        category = payload.category or classify_reason(payload.reason)
    except (httpx.HTTPError, KeyError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Classifier service unavailable") from error

    postponement = Postponement(
        person_id=payload.person_id,
        type=payload.type,
        reason=payload.reason,
        category=category,
        training_year=payload.training_year,
        education_record_id=payload.education_record_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        credited_hours=payload.credited_hours,
        source_file=payload.source_file,
        classifier_submission_id=payload.classifier_submission_id,
    )
    db.add(postponement)
    db.flush()
    recalculate_person(
        db, payload.person_id, 1, "postponement_created", _actor_value(actor),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(postponement)
    return postponement


def _decide_postponement(
    postponement: Postponement, decision: str, db: Session, actor: User
) -> Postponement:
    if postponement.status != "pending":
        raise HTTPException(status_code=409, detail="Postponement has already been decided")
    if postponement.classifier_submission_id:
        try:
            decide_submission(postponement.classifier_submission_id, decision)
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail="Classifier decision synchronization failed") from error
    postponement.status = "approved" if decision == "approved" else "rejected"
    postponement.approved_at = datetime.utcnow() if decision == "approved" else None
    postponement.decided_by = _actor_value(actor)
    reason = (
        "deferral_approved" if decision == "approved" and postponement.type in {"delay", "연기"}
        else "hold_approved" if decision == "approved"
        else "postponement_rejected"
    )
    recalculate_person(
        db, postponement.person_id, 1, reason, _actor_value(actor),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(postponement)
    return postponement


@router.patch("/{postponement_id}/approve", response_model=PostponementRead)
def approve_postponement(
    postponement_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(postponement, "approved", db, actor)


@router.patch("/{postponement_id}/reject", response_model=PostponementRead)
def reject_postponement(
    postponement_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(postponement, "declined", db, actor)


@router.patch("/{postponement_id}", response_model=PostponementRead)
def update_postponement(
    postponement_id: int,
    payload: PostponementUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_scheduler),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    if postponement.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending postponements can be edited")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(postponement, key, value)
    if postponement.start_date and postponement.end_date and postponement.end_date < postponement.start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    recalculate_person(
        db, postponement.person_id, 1, "postponement_edited", _actor_value(actor),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(postponement)
    return postponement


@router.patch("/{postponement_id}/revoke", response_model=PostponementRead)
def revoke_postponement(
    postponement_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    if postponement.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved postponements can be revoked")
    postponement.status = "revoked"
    postponement.decided_by = _actor_value(actor)
    recalculate_person(
        db, postponement.person_id, 1, "postponement_revoked", _actor_value(actor),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(postponement)
    return postponement


@router.patch("/{postponement_id}/resolve", response_model=PostponementRead)
def report_hold_resolution(
    postponement_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    if postponement.status != "approved" or (postponement.type or "").lower() not in {"hold", "보류", "법규보류", "방침보류"}:
        raise HTTPException(status_code=409, detail="Only approved holds can be resolved")
    if postponement.end_date is None:
        raise HTTPException(status_code=422, detail="Hold end date is required")
    today = date.today()
    if today < postponement.end_date:
        raise HTTPException(status_code=409, detail="The hold period has not ended")
    if (today - postponement.end_date).days > HOLD_RESOLUTION_GRACE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Hold resolution report is outside the {HOLD_RESOLUTION_GRACE_DAYS}-day window",
        )
    postponement.resolution_reported_at = datetime.utcnow()
    postponement.decided_by = _actor_value(actor)
    recalculate_person(
        db, postponement.person_id, 1, "hold_ended", _actor_value(actor),
        actor_user_id=actor.id,
    )
    db.commit()
    db.refresh(postponement)
    return postponement