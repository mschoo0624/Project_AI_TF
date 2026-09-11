"""Reservist API routes."""
# 인원 및군종, 계급 상태.

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate, PersonRead, PersonUpdate

router = APIRouter(prefix="/reservists", tags=["reservists"])

@router.get("", response_model=list[PersonRead])
def list_reservists(
	branch: str | None = Query(default=None),
	rank: str | None = Query(default=None),
	status: str | None = Query(default=None),
	db: Session = Depends(get_db),
) -> list[Person]:
	query = select(Person)
	if branch:
		query = query.where(Person.branch == branch)
	if rank:
		query = query.where(Person.rank == rank)
	if status:
		query = query.where(Person.status == status)
	return list(db.scalars(query.order_by(Person.military_number)).all())

@router.get("/{military_number}", response_model=PersonRead)
def get_reservist(military_number: str, db: Session = Depends(get_db)) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	return person

@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_reservist(payload: PersonCreate, db: Session = Depends(get_db)) -> Person:
	person = Person(**payload.model_dump())
	db.add(person)
	try:
		db.commit()
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=409, detail="Military number already exists") from error
	db.refresh(person)
	return person

@router.patch("/{military_number}", response_model=PersonRead)
def update_reservist(
	military_number: str,
	payload: PersonUpdate,
	db: Session = Depends(get_db),
) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")

	for field, value in payload.model_dump(exclude_unset=True).items():
		setattr(person, field, value)
	db.commit()
	db.refresh(person)
	return person

@router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservist(military_number: str, db: Session = Depends(get_db)) -> None:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	db.delete(person)
	db.commit()
