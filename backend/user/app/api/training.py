"""Reserve-training hour APIs."""
"""
훈련시간과 연간 훈련 진행률을 관리합니다.

라우터 기본 경로는 /reservists이지만 실제 기능은 훈련시간 주소에 붙습니다.

GET 기능
다음 정보를 반환합니다.

현재 복무연도
연도별 훈련 진행률
연도별 동원 상태
목표 훈련시간
이월시간
남은 시간
고발 위험
실제 교육 기록
POST 기능
훈련 기록을 등록합니다.

검증하는 항목:

미래 복무연도인지 여부
훈련시간이 양수인지 여부
불참 기록인데 시간이 입력됐는지 여부
목표시간보다 많은 시간이 등록됐는지 여부
출석 상태가 유효한지 여부
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.education import (
	TrainingRecordCreate,
	TrainingRecordRead,
	TrainingRecordUpdate,
)
from user.app.services.training import (
	all_training_progress,
    COMPLETED,
)

router = APIRouter(prefix="/reservists", tags=["training"])
persons_training_router = APIRouter(prefix="/persons", tags=["training"])


def _get_person_or_404(military_number: str, db: Session) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	return person


@persons_training_router.get("/{military_number}/training-progress")
def get_training_progress(
	military_number: str,
	db: Session = Depends(get_db),
) -> list[dict[str, object]]:
	person = _get_person_or_404(military_number, db)
	return all_training_progress(db, person)


@router.get("/{military_number}/training-hours")
def get_training_hours(
	military_number: str,
	db: Session = Depends(get_db),
) -> dict[str, object]:
	person = _get_person_or_404(military_number, db)

	return {
		"military_number": military_number,
		"current_service_year": person.service_year,
		"progress": all_training_progress(db, person),
		"records": [
			{
				"id": record.id,
				"education_year": record.education_year,
				"training_year": record.training_year,
				"training_type": record.training_type,
				"training_round": record.training_round,
				"mobilization_status": next(
					(
						status.mobilization_status
						for status in person.annual_statuses
						if status.service_year == record.education_year
					),
					person.mobilization_status,
				),
				"attendance_status": record.attendance_status,
				"training_hours": record.training_hours,
				"notes": record.notes,
			}
			for record in db.scalars(
				select(Education)
				.where(Education.person_id == military_number)
				.order_by(Education.education_year, Education.training_year, Education.id)
			).all()
		],
	}

@router.post(
	"/{military_number}/training-hours",
	response_model=TrainingRecordRead,
	status_code=status.HTTP_201_CREATED,
)
def add_training_record(
	military_number: str,
	payload: TrainingRecordCreate,
	db: Session = Depends(get_db),
) -> Education:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	if person.service_year is not None and payload.service_year > person.service_year:
		raise HTTPException(
		status_code=400,
		detail="Cannot record training for a future service year",
	)

	progress = all_training_progress(db, person)
	# Progress includes year 0, so the service year is its list index.
	year_progress = progress[payload.service_year]
	target = int(year_progress["required_hours"])
	if target == 0:
		raise HTTPException(
		status_code=400,
		detail="This service year has no configured training requirement",
	)
	completed = int(year_progress["completed_hours"])
	if payload.attendance_status not in COMPLETED and payload.attendance_status not in {
		"연기",
		"postponed",
		"무단불참",
		"무단_불참",
		"unexcused_absence",
	}:
		raise HTTPException(status_code=422, detail="Invalid attendance status")
	if payload.attendance_status in COMPLETED and payload.training_hours == 0:
		raise HTTPException(status_code=422, detail="Completed training must include positive hours")
	if payload.attendance_status not in COMPLETED and payload.training_hours != 0:
		raise HTTPException(status_code=422, detail="Non-completed training must have zero hours")
	if payload.attendance_status in COMPLETED and payload.training_hours > target - completed:
		raise HTTPException(
		status_code=400,
		detail=f"Training hours exceed the remaining allowance ({max(target - completed, 0)} hours)",
	)

	record = Education(
		person_id=military_number,
		education_year=payload.service_year,
		training_year=payload.training_year or person.service_year or payload.service_year,
		training_type=payload.training_type,
		training_round=payload.training_round,
		attendance_status=payload.attendance_status,
		training_hours=payload.training_hours,
		notes=payload.notes,
	)
	db.add(record)
	db.commit()
	db.refresh(record)
	return record


@router.patch(
	"/{military_number}/training-hours/{record_id}",
	response_model=TrainingRecordRead,
)
def update_training_record(
	military_number: str,
	record_id: int,
	payload: TrainingRecordUpdate,
	db: Session = Depends(get_db),
) -> Education:
	_get_person_or_404(military_number, db)
	record = db.get(Education, record_id)
	if record is None or record.person_id != military_number:
		raise HTTPException(status_code=404, detail="Training record not found")
	for field, value in payload.model_dump(exclude_unset=True).items():
		setattr(record, "education_year" if field == "service_year" else field, value)
	db.commit()
	db.refresh(record)
	return record


@router.delete("/{military_number}/training-hours/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_record(
	military_number: str,
	record_id: int,
	db: Session = Depends(get_db),
) -> None:
	_get_person_or_404(military_number, db)
	record = db.get(Education, record_id)
	if record is None or record.person_id != military_number:
		raise HTTPException(status_code=404, detail="Training record not found")
	db.delete(record)
	db.commit()