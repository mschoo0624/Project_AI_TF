from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.api.transfers import confirm_transfer_intake, submit_transfer_intake
from user.app.models.assignment import Assignment
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.models.transfer_intake import TransferIntake
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


def test_officer_type_two_makeup_round_accepts_32_hours() -> None:
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
				training_hours=32,
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