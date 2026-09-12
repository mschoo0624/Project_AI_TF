"""Reservist API routes."""
# 예비군 인원 관리 API입니다.
"""
기능 설명:

전체 인원 조회
군번으로 특정 인원 조회
인원 등록
인원 정보 수정
인원 삭제
군종, 계급, 상태로 필터링
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate, PersonRead, PersonUpdate

router = APIRouter(prefix="/reservists", tags=["reservists"])
persons_router = APIRouter(prefix="/persons", tags=["persons"])

@router.get("", response_model=list[PersonRead])
@persons_router.get("", response_model=list[PersonRead])
def list_reservists(
	query_text: str | None = Query(default=None, alias="query"),
	branch: str | None = Query(default=None),
	rank: str | None = Query(default=None),
	status: str | None = Query(default=None),
	mobilization_status: str | None = Query(default=None),
	db: Session = Depends(get_db),
) -> list[Person]:
	query = select(Person)
	if query_text:
		search = f"%{query_text}%"
		query = query.where(or_(Person.name.like(search), Person.military_number.like(search)))
	if branch:
		query = query.where(Person.branch == branch)
	if rank:
		query = query.where(Person.rank == rank)
	if status:
		query = query.where(Person.status == status)
	if mobilization_status:
		query = query.where(Person.mobilization_status == mobilization_status)
	return list(db.scalars(query.order_by(Person.military_number)).all())

@router.get("/{military_number}", response_model=PersonRead)
@persons_router.get("/{military_number}", response_model=PersonRead)
def get_reservist(military_number: str, db: Session = Depends(get_db)) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	return person

@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
@persons_router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
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
@persons_router.patch("/{military_number}", response_model=PersonRead)
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
@persons_router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservist(military_number: str, db: Session = Depends(get_db)) -> None:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	db.delete(person)
	db.commit()
