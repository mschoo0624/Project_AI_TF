"""Reserve-training hour APIs."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.education import TrainingRecordCreate, TrainingRecordRead
from user.app.services.training import (
	all_training_progress,
    COMPLETED,
)

router = APIRouter(prefix="/reservists", tags=["training"])


@router.get("/{military_number}/training-hours")
def get_training_hours(
	military_number: str,
	db: Session = Depends(get_db),
) -> dict[str, object]:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")

	return {
		"military_number": military_number,
		"current_service_year": person.service_year,
		"progress": all_training_progress(db, person),
		"records": [
			{
				"id": record.id,
				"education_year": record.education_year,
				"training_year": record.training_year,
				"training_round": record.training_round,
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
	year_progress = progress[payload.service_year - 1]
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
		training_year=person.service_year or payload.service_year,
		training_round=payload.training_round,
		attendance_status=payload.attendance_status,
		training_hours=payload.training_hours,
		notes=payload.notes,
	)
	db.add(record)
	db.commit()
	db.refresh(record)
	return record