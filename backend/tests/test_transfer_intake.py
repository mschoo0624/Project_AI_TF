from datetime import date

from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.api.transfers import confirm_transfer_intake, submit_transfer_intake
from user.app.models.assignment import Assignment
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.models.transfer_intake import TransferIntake
from user.app.models.training_recalculation import TrainingCarryover, TrainingRoundState, TrainingYearResult
from user.app.schemas.transfer_intake import (
	TransferIntakeCreate,
	TransferPersonDetails,
	TransferTrainingRecord,
)


def make_session() -> Session:
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)
	from user.app import models  # noqa: F401

	models.Person.metadata.create_all(engine)
	return Session(engine)


def transfer_payload() -> TransferIntakeCreate:
	return TransferIntakeCreate(
		person=TransferPersonDetails(
			military_number="26-70000030",
			name="전입예비군",
			branch="육군",
			rank="병장",
			service_year=2,
			position="소총수",
			mobilization_status="동원지정",
		),
		training_records=[
			TransferTrainingRecord(
				service_year=1,
				training_year=2025,
				training_type="동원훈련Ⅰ형",
				training_round=1,
				training_hours=28,
			),
		],
	)


def test_transfer_stays_out_of_roster_until_confirmed() -> None:
	db = make_session()
	db.add(Squad(id=1, name="육군 병사 1분대"))
	db.commit()
	transfer = submit_transfer_intake(transfer_payload(), db)

	assert transfer.status == "pending"
	assert db.get(Person, "26-70000030") is None
	assert db.scalars(select(Education)).all() == []

	confirmed = confirm_transfer_intake(transfer.id, db)
	person = db.get(Person, "26-70000030")
	records = db.scalars(
		select(Education).where(Education.person_id == "26-70000030")
	).all()

	assert confirmed.status == "confirmed"
	assert confirmed.assigned_squad_id == 1
	assert person is not None
	assert person.registration_type == "예비군 전입"
	assert person.squad_id == 1
	assert db.scalars(select(Assignment).where(Assignment.person_id == person.military_number)).one().squad_id == 1
	assert len(records) == 1
	assert records[0].education_year == 1
	assert records[0].training_year == 2025
	assert records[0].training_type == "동원훈련Ⅰ형"
	assert records[0].training_hours == 28
	db.close()


def test_transfer_confirmation_requires_compatible_squad() -> None:
	db = make_session()
	transfer = submit_transfer_intake(transfer_payload(), db)

	try:
		confirm_transfer_intake(transfer.id, db)
		assert False, "confirmation should fail when no squad is available"
	except HTTPException as error:
		assert error.status_code == 409

	stored_transfer = db.get(TransferIntake, transfer.id)
	assert stored_transfer is not None
	assert stored_transfer.status == "pending"
	assert db.get(Person, "26-70000030") is None
	db.close()


def test_officer_type_two_round_accepts_28_hours() -> None:
	payload = TransferIntakeCreate(
		person=TransferPersonDetails(
			military_number="26-70000031",
			name="간부 전입예비군",
			branch="육군",
			rank="하사",
			service_year=2,
			position="분대장",
			mobilization_status="동원미지정",
		),
		training_records=[
			TransferTrainingRecord(
				service_year=2,
				training_year=2026,
				training_type="동원훈련Ⅱ형",
				training_round=2,
				training_hours=28,
			),
		],
	)
	db = make_session()

	transfer = submit_transfer_intake(payload, db)
	assert transfer.status == "pending"
	db.close()


def test_officer_type_two_carryover_uses_32_hour_target() -> None:
	payload = TransferIntakeCreate(
		person=TransferPersonDetails(
			military_number="26-70000032",
			name="간부 이월 전입예비군",
			branch="육군",
			rank="하사",
			service_year=2,
			position="분대장",
			mobilization_status="동원미지정",
		),
		training_records=[
			TransferTrainingRecord(
				service_year=1,
				training_year=2025,
				training_type="동원훈련Ⅱ형",
				training_hours=20,
			),
			TransferTrainingRecord(
				service_year=2,
				training_year=2026,
				training_type="동원훈련Ⅱ형",
				training_hours=32,
			),
		],
	)
	db = make_session()

	transfer = submit_transfer_intake(payload, db)
	assert transfer.status == "pending"
	db.close()


def test_transfer_preserves_confirmed_round_one_absence_and_current_year_completion() -> None:
	db = make_session()
	db.add(Squad(id=1, name="육군 병사 1분대"))
	db.commit()
	payload = TransferIntakeCreate(
		person=TransferPersonDetails(
			military_number="26-70000040",
			name="차수 전입",
			branch="육군",
			rank="병장",
			service_year=2,
			position="소총수",
			mobilization_status="동원미지정",
		),
		training_records=[
			TransferTrainingRecord(
				service_year=1,
				training_year=date.today().year - 1,
				training_type="동원훈련Ⅱ형",
				training_round=1,
				training_hours=0,
				attendance_status="무단불참",
				confirmed_by="전 소속 확인자",
			),
			TransferTrainingRecord(
				service_year=1,
				training_year=date.today().year - 1,
				training_type="동원훈련Ⅱ형",
				training_round=2,
				training_hours=0,
				attendance_status="무단불참",
				confirmed_by="전 소속 확인자",
			),
			TransferTrainingRecord(
				service_year=2,
				training_year=date.today().year,
				training_type="기본훈련",
				training_round=1,
				training_hours=8,
			),
		],
	)
	transfer = submit_transfer_intake(payload, db)
	confirm_transfer_intake(transfer.id, db)

	carryover = db.scalars(select(TrainingCarryover).where(
		TrainingCarryover.person_id == payload.person.military_number,
		TrainingCarryover.origin_year == 1,
	)).one()
	round_state = db.scalars(select(TrainingRoundState).where(
		TrainingRoundState.person_id == payload.person.military_number,
		TrainingRoundState.training_type == "동원훈련Ⅱ형",
	)).one()
	current_result = db.scalars(select(TrainingYearResult).where(
		TrainingYearResult.person_id == payload.person.military_number,
		TrainingYearResult.service_year == 2,
		TrainingYearResult.training_type == "동원훈련Ⅰ형",
	)).one()
	assert carryover.current_round == 3
	assert round_state.current_round == 3
	assert current_result.unmet_hours == 0
	db.close()


def test_transfer_no_show_requires_confirming_person() -> None:
	with pytest.raises(ValidationError, match="confirmed_by"):
		TransferTrainingRecord(
			service_year=1,
			training_year=2025,
			training_type="동원훈련Ⅰ형",
			training_hours=0,
			attendance_status="무단불참",
		)