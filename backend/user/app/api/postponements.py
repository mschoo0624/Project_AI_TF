"""Postponement API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.postponement import Postponement
from user.app.schemas.postponement import PostponementCreate, PostponementRead

router = APIRouter(prefix="/postponements", tags=["postponements"])

@router.get("", response_model=list[PostponementRead])
def list_postponements(
	status: str | None = Query(default=None),
	db: Session = Depends(get_db),
) -> list[Postponement]:
	query = select(Postponement).order_by(Postponement.id)
	if status:
		query = query.where(Postponement.status == status)
	return list(db.scalars(query).all())


@router.post("", response_model=PostponementRead, status_code=status.HTTP_201_CREATED)
def create_postponement(
	payload: PostponementCreate,
	db: Session = Depends(get_db),
) -> Postponement:
	if db.get(Person, payload.person_id) is None:
		raise HTTPException(status_code=404, detail="Reservist not found")

	postponement = Postponement(**payload.model_dump())
	db.add(postponement)
	db.commit()
	db.refresh(postponement)
	return postponement


def update_postponement_status(
	postponement_id: int,
	new_status: str,
	db: Session,
) -> Postponement:
	postponement = db.get(Postponement, postponement_id)
	if postponement is None:
		raise HTTPException(status_code=404, detail="Postponement not found")

	postponement.status = new_status
	if new_status == "approved":
		postponement.approved_at = datetime.now()
	db.commit()
	db.refresh(postponement)
	return postponement


@router.patch("/{postponement_id}/approve", response_model=PostponementRead)
def approve_postponement(
	postponement_id: int,
	db: Session = Depends(get_db),
) -> Postponement:
	return update_postponement_status(postponement_id, "approved", db)


@router.patch("/{postponement_id}/reject", response_model=PostponementRead)
def reject_postponement(
	postponement_id: int,
	db: Session = Depends(get_db),
) -> Postponement:
	return update_postponement_status(postponement_id, "rejected", db)
