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

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.annual_status import AnnualStatus
from user.app.models.assignment import Assignment
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate, PersonRead, PersonUpdate, PersonProfileUpdate
from user.app.services.person_profile import ProfileError, profile_options, save_profile
from user.app.services.assignment import grouped_candidates, is_assignable, not_assignable_reason
from user.app.services.person import create_person
from user.app.services.person_search import PersonSearch, search_people
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
	platoon: str | None = Query(default=None, description="소대 이름, 예: 1소대"),
	category: Literal["병사", "부사관", "장교", "간부"] | None = Query(default=None),
	assigned: bool | None = Query(default=None, description="true=편성, false=미편성"),
	db: Session = Depends(get_db),
) -> list[Person]:
	return search_people(db, PersonSearch(
		query_text=query_text,
		branch=branch,
		rank=rank,
		status=status,
		mobilization_status=mobilization_status,
		platoon=platoon,
		category=category,
		assigned=assigned,
	))

@persons_router.get("/profile-options")
def get_profile_options():
	return profile_options()


@persons_router.patch("/{military_number}/profile", response_model=PersonRead)
def update_profile(military_number: str, payload: PersonProfileUpdate, db: Session = Depends(get_db)):
	person = _profile_person(db, military_number)
	try:
		return save_profile(db, person, payload.model_dump())
	except ProfileError as error:
		raise HTTPException(status_code=422, detail={"fields": error.fields}) from error
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=409, detail="군번 중복 또는 연결 정보 충돌로 저장하지 못했습니다.") from error


def _profile_person(db: Session, military_number: str):
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="대상자를 찾을 수 없습니다. 목록을 새로고침하세요.")
	return person


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
	if updates.get("squad_id") is not None and not is_assignable(person):
		db.rollback()
		raise HTTPException(status_code=409, detail=f"편성 대상이 아닙니다 ({not_assignable_reason(person)})")
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
