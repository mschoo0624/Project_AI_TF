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
from user.app.models.annual_status import AnnualStatus
from user.app.models.assignment import Assignment
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate, PersonRead, PersonUpdate
from user.app.services.assignment import grouped_candidates
from user.app.services.person import create_person
from user.app.services.training import all_training_progress, apply_mobilization_status_change

router = APIRouter(prefix="/reservists", tags=["reservists"])
persons_router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("/prosecution-targets")
def list_prosecution_targets(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	"""List reservists currently marked as prosecution targets by training rules."""
	people = db.scalars(select(Person).order_by(Person.military_number)).all()
	result: list[dict[str, object]] = []
	for person in people:
		progress = all_training_progress(db, person)
		targets = [item for item in progress if item.get("prosecution_status") == "고발대상자"]
		if not targets:
			continue
		latest = targets[-1]
		result.append({
			"military_number": person.military_number,
			"name": person.name,
			"branch": person.branch,
			"rank": person.rank,
			"service_year": person.service_year,
			"squad_id": person.squad_id,
			"mobilization_status": person.mobilization_status,
			"prosecution_reason": latest.get("prosecution_reason"),
			"consecutive_unexcused_absences": max(
				int(item.get("consecutive_unexcused_absences", 0)) for item in targets
			),
			"target_years": [int(item["service_year"]) for item in targets],
		})
	return result

@persons_router.get("/assignment-candidates")
def list_assignment_candidates(
	position: str = Query(..., description="Wartime position, for example 행정병"),
	branch: str | None = Query(default=None),
	db: Session = Depends(get_db),
) -> dict[str, dict[str, list[dict[str, object]]]]:
	
	people = db.scalars(select(Person).order_by(Person.military_number)).all()
	groups = grouped_candidates(people, position, branch)
	return {
		branch_name: {
			personnel_category: [
				{
					"military_number": candidate.person.military_number,
					"name": candidate.person.name,
					"rank": candidate.person.rank,
					"service_year": candidate.person.service_year,
					"specialty": candidate.person.specialty,
					"position": candidate.person.position,
					"tier": candidate.tier,
				}
				for candidate in candidates
			]
			for personnel_category, candidates in personnel_groups.items()
		}
		for branch_name, personnel_groups in groups.items()
	}

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
	try:
		return create_person(db, payload)
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=409, detail="Military number already exists") from error

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

	updates = payload.model_dump(exclude_unset=True)
	new_mobilization_status = updates.pop("mobilization_status", None)
	for field, value in updates.items():
		setattr(person, field, value)
	if new_mobilization_status is not None and new_mobilization_status != person.mobilization_status:
		apply_mobilization_status_change(db, person, new_mobilization_status)
	db.commit()
	db.refresh(person)
	return person

@router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT)
@persons_router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservist(military_number: str, db: Session = Depends(get_db)) -> None:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	for model in (AnnualStatus, Assignment, Education):
		db.query(model).filter(model.person_id == military_number).delete(
			synchronize_session=False
		)
	db.delete(person)
	db.commit()
