"""Postponement API backed by the separate classifier service."""

from datetime import date, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.education import Education
from user.app.models.postpoment import Postponement
from user.app.models.user import User
from user.app.schemas.postponement import PostponementCreate, PostponementRead, PostponementUpdate
from user.app.services.classifier_client import (
    classify_reason,
    decide_submission,
    get_submission,
    verify_documents,
)
from user.app.services.auth import require_approver, require_scheduler, require_viewer
from user.app.services.training_recalculation import (
    HOLD_RESOLUTION_GRACE_DAYS,
    recalculate_person,
)


router = APIRouter(prefix="/postponements", tags=["postponements"])


def _actor_value(actor: User) -> str:
    return actor.username[:100]


class VerificationInput(BaseModel):
    person_id: str
    education_id: int | None = None
    documents: list[dict] = Field(min_length=1, max_length=20)
    context: dict = Field(default_factory=dict)
    submission_id: str | None = None


@router.post('/verify')
def verify_postponement(payload: VerificationInput, db: Session = Depends(get_db)):
    person = db.get(Person, payload.person_id)
    if person is None:
        raise HTTPException(404, '대상자를 찾을 수 없습니다.')
    context = dict(payload.context)
    # Database identity always overrides caller-supplied values.
    for key, value in [('applicant_name', person.name), ('applicant_service_number', person.military_number)]:
        context[key] = {'value': value, 'source': f'person:{person.military_number}'}
    if payload.education_id is not None:
        education = db.get(Education, payload.education_id)
        if education is None or education.person_id != person.military_number:
            raise HTTPException(404, '해당 대상자의 훈련을 찾을 수 없습니다.')
        context['training_start'] = {'value': education.scheduled_date.isoformat() if education.scheduled_date else None,
                                     'source': f'education:{education.id}:scheduled_date'}
        # No end-date column or comprehensive MMA history exists: never invent either.
    try:
        if payload.submission_id:
            import re
            if not re.fullmatch(r'qwen_[0-9a-f]{32}', payload.submission_id): raise HTTPException(422, '잘못된 제출 ID입니다.')
            return verify_documents(payload.documents, context, payload.submission_id)
        return verify_documents(payload.documents, context)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            raise HTTPException(422, '검증 입력 형식이나 외부 확인값을 확인하세요.') from exc
        raise HTTPException(502, '검증 서비스를 사용할 수 없습니다.') from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, '검증 서비스를 사용할 수 없습니다.') from exc


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

    if payload.classifier_submission_id:
        existing = db.scalar(select(Postponement).where(Postponement.classifier_submission_id == payload.classifier_submission_id))
        if existing:
            if existing.person_id != payload.person_id: raise HTTPException(409, '다른 대상자에게 연결된 신청입니다.')
            return existing

        if payload.classifier_submission_id.startswith('qwen_'):
            import re
            if not re.fullmatch(r'qwen_[0-9a-f]{32}', payload.classifier_submission_id): raise HTTPException(422, '잘못된 제출 ID입니다.')
            try:
                submission = get_submission(payload.classifier_submission_id)
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(502, '제출 원본을 확인하지 못했습니다.') from exc
            if submission['military_number'] != payload.person_id: raise HTTPException(409, '제출 대상자가 일치하지 않습니다.')
            payload.category = submission['application_type']
            payload.reason = submission['reason_category']
            payload.source_file = submission['filename']
            payload.type = 'delay' if submission['application_type'].startswith('postponement.') else 'hold'

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
    postponement: Postponement,
    decision: str,
    db: Session,
    actor: User,
    note: str | None = None,
) -> Postponement:
    target = 'approved' if decision == 'approved' else 'rejected'
    if postponement.status == target:
        return postponement
    if postponement.status != "pending":
        raise HTTPException(status_code=409, detail="Postponement has already been decided")
    if postponement.classifier_submission_id:
        try:
            decide_submission(postponement.classifier_submission_id, decision, note)
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


class DecisionNote(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.patch("/{postponement_id}/approve", response_model=PostponementRead)
def approve_postponement(
    postponement_id: int,
    payload: DecisionNote | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(
        postponement, "approved", db, actor, payload.note if payload else None
    )


@router.patch("/{postponement_id}/reject", response_model=PostponementRead)
def reject_postponement(
    postponement_id: int,
    payload: DecisionNote | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_approver),
) -> Postponement:
    postponement = db.get(Postponement, postponement_id)
    if postponement is None:
        raise HTTPException(status_code=404, detail="Postponement not found")
    return _decide_postponement(
        postponement, "declined", db, actor, payload.note if payload else None
    )


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
