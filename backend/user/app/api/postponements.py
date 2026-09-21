"""Postponement API backed by the separate classifier service."""

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.schemas.postponement import PostponementCreate, PostponementRead
from user.app.services.classifier_client import classify_reason, decide_submission


router = APIRouter(prefix="/postponements", tags=["postponements"])


@router.get("", response_model=list[PostponementRead])
def list_postponements(db: Session = Depends(get_db)) -> list[Postponement]:
    return list(db.scalars(select(Postponement).order_by(Postponement.id.desc())).all())


@router.post("", response_model=PostponementRead, status_code=status.HTTP_201_CREATED)
def create_postponement(
    payload: PostponementCreate,
    db: Session = Depends(get_db),
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
        source_file=payload.source_file,
        classifier_submission_id=payload.classifier_submission_id,
    )
    db.add(postponement)
    db.commit()
    db.refresh(postponement)
    return postponement


def _decide_postponement(postponement: Postponement, decision: str, db: Session) -> Postponement:
    if postponement.status != "pending":
        raise HTTPException(status_code=409, detail="Postponement has already been decided")
    if postponement.classifier_submission_id:
        try:
            decide_submission(postponement.classifier_submission_id, decision)
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail="Classifier decision synchronization failed") from error
    postponement.status = "approved" if decision == "approved" else "rejected"
    postponement.approved_at = datetime.utcnow() if decision == "approved" else None
    db.commit()
    db.refresh(postponement)
    return postponement


@router.patch("/{postponement_id}/approve", response_model=PostponementRead)
def approve_postponement(postponement_id: int, db: Session = Depends(get_db)) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(postponement, "approved", db)


@router.patch("/{postponement_id}/reject", response_model=PostponementRead)
def reject_postponement(postponement_id: int, db: Session = Depends(get_db)) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(postponement, "declined", db)