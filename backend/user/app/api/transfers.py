"""Transfer-in submission and review endpoints."""

import json
from datetime import datetime, timezone
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.transfer_intake import TransferIntake
from user.app.models.user import User
from user.app.models.training_recalculation import TrainingCarryover
from user.app.schemas.transfer_intake import (
	TransferIntakeCreate,
	TransferIntakeRead,
)
from user.app.services.assignment import (
	confirm_assignment_selections,
	recommend_squads_for_person,
)
from user.app.services.auth import require_approver, require_scheduler, require_viewer
from user.app.services.training import (
	NON_DESIGNATED_OR_UNSET,
	TYPE_II_TRAINING_NAMES,
	is_local_reserve_command_position,
	is_officer_reservist,
	target_training_hours,
	training_plan_has_type,
)
from user.app.services.training_recalculation import recalculate_person

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _read_transfer(
	transfer: TransferIntake,
	assigned_squad_id: int | None = None,
) -> TransferIntakeRead:
	return TransferIntakeRead.model_validate(transfer).model_copy(
		update={"assigned_squad_id": assigned_squad_id,
		        "carryovers": transfer.carryovers or []}
	)


def _validate_training_hours(payload: TransferIntakeCreate) -> None:
	totals: dict[int, int] = {}
	for record in payload.training_records:
		if record.attendance_status in {"이수", "completed", "참석", "attended"}:
			totals[record.service_year] = totals.get(record.service_year, 0) + record.training_hours

	carryover = 0
	for service_year in range(1, payload.person.service_year + 1):
		person = payload.person
		has_type_ii = training_plan_has_type(
			"동원훈련Ⅱ형",
			service_year,
			person.mobilization_status,
			person.branch,
			person.rank,
			person.position,
		)
		prior_failed_attempts = sum(
			record.service_year == service_year
			and "".join(record.training_type.split()) in TYPE_II_TRAINING_NAMES
			and (
			    (
			        record.attendance_status in {"무단불참", "무단_불참", "unexcused_absence"}
			        and bool(record.confirmed_by and record.confirmed_by.strip())
			    )
			    or record.attendance_status in {"연기", "postponed"}
			)
			for record in payload.training_records
		)
		officer_type_ii_makeup = (
			is_officer_reservist(person.rank)
			and has_type_ii
			and (carryover > 0 or prior_failed_attempts >= 2)
		)
		target = target_training_hours(
			service_year,
			person.mobilization_status,
			person.branch,
			person.rank,
			person.position,
			officer_type_ii_makeup,
		)
		required = target + carryover
		hours = totals.get(service_year, 0)
		if hours > required:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=f"Year {service_year} training hours exceed the {required}-hour requirement including carryover",
			)
		carryover = required - hours


@router.get("", response_model=list[TransferIntakeRead])
def list_transfer_intakes(
	status_filter: Literal["pending", "confirmed", "rejected", "all"] = Query(
		default="pending", alias="status"
	),
	db: Session = Depends(get_db),
	_viewer: User = Depends(require_viewer),
) -> list[TransferIntakeRead]:
	query = select(TransferIntake, Person.squad_id).outerjoin(
		Person, Person.military_number == TransferIntake.military_number
	)
	if status_filter != "all":
		query = query.where(TransferIntake.status == status_filter)
	rows = db.execute(query.order_by(TransferIntake.submitted_at.desc())).all()
	return [_read_transfer(transfer, squad_id) for transfer, squad_id in rows]


@router.post("", response_model=TransferIntakeRead, status_code=status.HTTP_201_CREATED,
	dependencies=[Depends(require_scheduler)])
def submit_transfer_intake(
	payload: TransferIntakeCreate,
	db: Session = Depends(get_db),
	actor: User | None = Depends(require_scheduler),
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
		person_details=payload.person.model_dump(mode="json"),
		training_records=[record.model_dump() for record in payload.training_records],
		carryovers=[record.model_dump() for record in payload.carryovers],
	)
	db.add(transfer)
	db.flush()
	if isinstance(actor, User):
		db.add(AuditLog(
			user_id=actor.id,
			action="transfer.submit",
			table_name="transfer_intake",
			record_id=transfer.id,
			entity_key=transfer.military_number,
			actor_label=actor.username,
			before_data=json.dumps({"status": None}, sort_keys=True),
			after_data=json.dumps({"status": transfer.status}, sort_keys=True),
		))
	db.commit()
	db.refresh(transfer)
	return _read_transfer(transfer)


@router.patch("/{transfer_id}/confirm", response_model=TransferIntakeRead,
	dependencies=[Depends(require_approver)])
def confirm_transfer_intake(
	transfer_id: int,
	db: Session = Depends(get_db),
	actor: User | None = Depends(require_approver),
) -> TransferIntakeRead:
	transfer = db.get(TransferIntake, transfer_id)
	if transfer is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer submission not found")
	if transfer.status != "pending":
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer submission is no longer pending")
	if db.get(Person, transfer.military_number) is not None:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Military number already exists")

	person_details = dict(transfer.person_details)
	for date_field in ("discharge_date", "callup_release_date"):
		if isinstance(person_details.get(date_field), str):
			person_details[date_field] = date.fromisoformat(person_details[date_field])
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
			attendance_status=item.get("attendance_status", "completed"),
			training_hours=item["training_hours"],
			source_kind="transfer",
			confirmed_by=item.get("confirmed_by"),
			notes=item.get("notes"),
		))
	for item in transfer.carryovers or []:
		db.add(TrainingCarryover(
			person_id=transfer.military_number,
			origin_year=item["origin_year"],
			training_type=item["training_type"],
			origin_round=item["origin_round"],
			current_round=item["current_round"],
			original_hours=item["hours"],
			imported_hours=item["hours"],
			remaining_hours=item["hours"],
			status="open",
			reason_code="transfer_import",
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
			commit=False,
			actor_user_id=actor.id if isinstance(actor, User) else None,
			actor_label=actor.username if isinstance(actor, User) else "transfer intake",
		)
		recalculate_person(
			db, person.military_number, 1, "transfer", actor.username if isinstance(actor, User) else "transfer intake",
			actor_user_id=actor.id if isinstance(actor, User) else None,
		)
		if isinstance(actor, User):
			db.add(AuditLog(
				user_id=actor.id,
				action="transfer.confirm",
				table_name="transfer_intake",
				record_id=transfer.id,
				entity_key=transfer.military_number,
				actor_label=actor.username,
				before_data=json.dumps({"status": "pending"}, sort_keys=True),
				after_data=json.dumps({"status": transfer.status, "assigned_squad_id": person.squad_id}, sort_keys=True),
			))
		db.commit()
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to confirm transfer submission") from error
	except ValueError as error:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
	db.refresh(transfer)
	assigned_squad_id = int(assignment["assigned"][0]["squad_id"])
	return _read_transfer(transfer, assigned_squad_id)


@router.patch("/{transfer_id}/reject", response_model=TransferIntakeRead,
	dependencies=[Depends(require_approver)])
def reject_transfer_intake(
	transfer_id: int,
	db: Session = Depends(get_db),
	actor: User | None = Depends(require_approver),
) -> TransferIntakeRead:
	transfer = db.get(TransferIntake, transfer_id)
	if transfer is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer submission not found")
	if transfer.status != "pending":
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer submission is no longer pending")
	transfer.status = "rejected"
	transfer.reviewed_at = datetime.now(timezone.utc)
	if isinstance(actor, User):
		db.add(AuditLog(
			user_id=actor.id,
			action="transfer.reject",
			table_name="transfer_intake",
			record_id=transfer.id,
			entity_key=transfer.military_number,
			actor_label=actor.username,
			before_data=json.dumps({"status": "pending"}, sort_keys=True),
			after_data=json.dumps({"status": transfer.status}, sort_keys=True),
		))
	db.commit()
	db.refresh(transfer)
	return _read_transfer(transfer)