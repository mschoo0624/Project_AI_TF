from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.models.person import Person
from user.app.schemas.education import TrainingRecordCreate, TrainingRecordUpdate
from user.app.api.training import add_training_record, update_training_record


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from user.app import models  # noqa: F401

    models.Person.metadata.create_all(engine)
    return Session(engine)


def test_cannot_exceed_training_hours_on_add_and_update() -> None:
    db = make_session()
    # 2년차 동원지정예비군 (2년차 목표시간: 28시간)
    person = Person(
        military_number="26-70000010",
        name="테스터",
        branch="육군",
        rank="병장",
        service_year=2,
        position="소총수",
        mobilization_status="동원지정",
        status="active",
    )
    db.add(person)
    db.commit()

    # 1. 2년차에 30시간 추가 시도 -> 초과(28시간)로 인해 400 에러 발생해야 함
    try:
        add_training_record(
            "26-70000010",
            TrainingRecordCreate(
                service_year=2,
                training_year=2,
                training_type="기본훈련",
                training_round=1,
                attendance_status="completed",
                training_hours=30,
            ),
            db,
        )
        assert False, "Should have raised HTTPException for exceeding hours"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "exceed the remaining allowance" in exc.detail

    # 2. 20시간 정상 등록
    record = add_training_record(
        "26-70000010",
        TrainingRecordCreate(
            service_year=2,
            training_year=2,
            training_type="기본훈련",
            training_round=1,
            attendance_status="completed",
            training_hours=20,
        ),
        db,
    )
    assert record.training_hours == 20

    # 3. 기존 20시간 기록을 35시간으로 수정 시도 -> 초과로 인해 400 에러 발생해야 함
    try:
        update_training_record(
            "26-70000010",
            record.id,
            TrainingRecordUpdate(training_hours=35),
            db,
        )
        assert False, "Should have raised HTTPException for exceeding hours on update"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "exceed the remaining allowance" in exc.detail

    # 4. 기존 20시간 기록을 28시간으로 수정 시도 -> 정상 수정 완료
    updated = update_training_record(
        "26-70000010",
        record.id,
        TrainingRecordUpdate(training_hours=28),
        db,
    )
    assert updated.training_hours == 28

    db.close()
