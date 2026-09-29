"""Transfer-in submission and review endpoints."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.transfer_intake import TransferIntake
from user.app.schemas.transfer_intake import (
	TransferIntakeCreate,
	TransferIntakeRead,
)
from user.app.services.assignment import (
	confirm_assignment_selections,
	recommend_squads_for_person,
)
from user.app.services.training import target_training_hours

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _read_transfer(
	transfer: TransferIntake,
	assigned_squad_id: int | None = None,
) -> TransferIntakeRead:
	return TransferIntakeRead.model_validate(transfer).model_copy(
		update={"assigned_squad_id": assigned_squad_id}
	)


def _validate_training_hours(payload: TransferIntakeCreate) -> None:
	totals: dict[int, int] = {}
	for record in payload.training_records:
		totals[record.service_year] = totals.get(record.service_year, 0) + record.training_hours

	for service_year, hours in totals.items():
		target = target_training_hours(
			service_year,
			payload.person.mobilization_status,
			payload.person.branch,
			payload.person.rank,
		)
		if hours > target:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=f"Year {service_year} training hours exceed the {target}-hour target",
			)


@router.get("", response_model=list[TransferIntakeRead])
def list_transfer_intakes(
	status_filter: Literal["pending", "confirmed", "rejected", "all"] = Query(
		default="pending", alias="status"
	),
	db: Session = Depends(get_db),
) -> list[TransferIntakeRead]:
	query = select(TransferIntake, Person.squad_id).outerjoin(
		Person, Person.military_number == TransferIntake.military_number
	)
	if status_filter != "all":
		query = query.where(TransferIntake.status == status_filter)
	rows = db.execute(query.order_by(TransferIntake.submitted_at.desc())).all()
	return [_read_transfer(transfer, squad_id) for transfer, squad_id in rows]


@router.post("", response_model=TransferIntakeRead, status_code=status.HTTP_201_CREATED)
def submit_transfer_intake(
	payload: TransferIntakeCreate,
	db: Session = Depends(get_db),
) -> TransferIntakeRead:
	if db.get(Person, payload.person.military_number) is not None:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Military number already exists")
	if db.scalar(
		select(TransferIntake.id).where(
			TransferIntake.military_number == payload.person.military_number,
			TransferIntake.status == "pending",
		)
	) is not None:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending transfer already exists for this military number")

	_validate_training_hours(payload)
	transfer = TransferIntake(
		military_number=payload.person.military_number,
		person_details=payload.person.model_dump(),
		training_records=[record.model_dump() for record in payload.training_records],
	)
	db.add(transfer)
	db.commit()
	db.refresh(transfer)
	return _read_transfer(transfer)


@router.patch("/{transfer_id}/confirm", response_model=TransferIntakeRead)
def confirm_transfer_intake(
	transfer_id: int,
	db: Session = Depends(get_db),
) -> TransferIntakeRead:
	transfer = db.get(TransferIntake, transfer_id)
	if transfer is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer submission not found")
	if transfer.status != "pending":
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer submission is no longer pending")
	if db.get(Person, transfer.military_number) is not None:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Military number already exists")

	person_details = dict(transfer.person_details)
	person_details["squad_id"] = None
	person_details["registration_type"] = "예비군 전입"
	person = Person(**person_details)
	db.add(person)
	db.flush()
	for item in transfer.training_records:
		db.add(Education(
			person_id=transfer.military_number,
			education_year=item["service_year"],
			training_year=item["training_year"],
			training_type=item["training_type"],
			training_round=item["training_round"],
			attendance_status="completed",
			training_hours=item["training_hours"],
			notes=item.get("notes"),
		))
	transfer.status = "confirmed"
	transfer.reviewed_at = datetime.now(timezone.utc)
	try:
		recommendations = recommend_squads_for_person(db, person.military_number)
		if not recommendations:
			db.rollback()
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="No compatible squad is available. Add a squad before confirming this transfer.",
			)
		assignment = confirm_assignment_selections(
			db,
			[(person.military_number, int(recommendations[0]["squad_id"]))],
		)
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to confirm transfer submission") from error
	except ValueError as error:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
	db.refresh(transfer)
	assigned_squad_id = int(assignment["assigned"][0]["squad_id"])
	return _read_transfer(transfer, assigned_squad_id)


@router.patch("/{transfer_id}/reject", response_model=TransferIntakeRead)
def reject_transfer_intake(
	transfer_id: int,
	db: Session = Depends(get_db),
) -> TransferIntakeRead:
	transfer = db.get(TransferIntake, transfer_id)
	if transfer is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer submission not found")
	if transfer.status != "pending":
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer submission is no longer pending")
	transfer.status = "rejected"
	transfer.reviewed_at = datetime.now(timezone.utc)
	db.commit()
	db.refresh(transfer)
	return _read_transfer(transfer)