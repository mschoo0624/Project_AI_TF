from datetime import date, timedelta
import json

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.models.person import Person
from user.app.models.education import Education
from user.app.models.audit_log import AuditLog
from user.app.models.postpoment import Postponement
from user.app.schemas.education import TrainingRecordCreate, TrainingRecordUpdate
from user.app.api.training import add_training_record, get_training_hours, update_training_record
from user.app.services.training import all_training_progress


def test_training_year_accepts_calendar_year_for_create_and_update() -> None:
    record = TrainingRecordCreate(
        service_year=3,
        training_year=2026,
        training_hours=8,
        attendance_status="completed",
    )
    update = TrainingRecordUpdate(training_year=2026)

    assert record.training_year == 2026
    assert update.training_year == 2026


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from user.app import models  # noqa: F401

    models.Person.metadata.create_all(engine)
    return Session(engine)


def test_scheduled_record_requires_and_returns_session_date() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100301",
        name="예정 훈련",
        branch="육군",
        rank="병장",
        service_year=1,
        position="소총수",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.commit()

    try:
        add_training_record(
            person.military_number,
            TrainingRecordCreate(
                service_year=1,
                training_type="기본훈련",
                attendance_status="scheduled",
                training_hours=0,
            ),
            db,
        )
        assert False, "Scheduled training must have a date"
    except HTTPException as error:
        assert error.status_code == 422

    scheduled_date = date.today() + timedelta(days=2)
    record = add_training_record(
        person.military_number,
        TrainingRecordCreate(
            service_year=1,
            training_year=scheduled_date.year,
            scheduled_date=scheduled_date,
            training_type="기본훈련",
            attendance_status="scheduled",
            training_hours=0,
        ),
        db,
    )

    data = get_training_hours(person.military_number, db)
    assert record.scheduled_date == scheduled_date
    assert data["records"][0]["scheduled_date"] == scheduled_date
    assert data["records"][0]["attendance_status"] == "scheduled"
    assert data["records"][0]["version"] == record.version
    assert data["records"][0]["version"] == record.version
    db.close()


def test_round_api_rejects_duplicate_and_skipped_rounds() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100302", name="차수 검증", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원미지정", status="active",
    )
    yesterday = date.today() - timedelta(days=1)
    db.add(person)
    db.add(Education(
        person_id=person.military_number, education_year=1, training_year=yesterday.year,
        scheduled_date=yesterday, training_type="기본훈련", training_round=1,
        attendance_status="무단불참", training_hours=0,
    ))
    db.commit()

    for round_number in (1, 3):
        try:
            add_training_record(
                person.military_number,
                TrainingRecordCreate(
                    service_year=1,
                    training_year=yesterday.year,
                    scheduled_date=yesterday,
                    training_type="기본훈련",
                    training_round=round_number,
                    attendance_status="무단불참",
                    training_hours=0,
                ),
                db,
            )
            assert False, "Duplicate or skipped rounds must be rejected"
        except HTTPException as error:
            assert error.status_code == 422
    db.close()


def test_future_completed_and_unexcused_records_are_rejected() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100303", name="날짜 검증", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.commit()
    future_date = date.today() + timedelta(days=1)

    for attendance_status, hours in (("completed", 8), ("무단불참", 0)):
        try:
            add_training_record(
                person.military_number,
                TrainingRecordCreate(
                    service_year=1,
                    training_year=future_date.year,
                    scheduled_date=future_date,
                    training_type="기본훈련",
                    attendance_status=attendance_status,
                    training_hours=hours,
                ),
                db,
            )
            assert False, "A future session cannot be completed or marked absent"
        except HTTPException as error:
            assert error.status_code == 422
    db.close()


def test_round_two_rejected_after_first_round_requirement_is_satisfied() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100304", name="이수 차수", branch="육군", rank="병장",
        service_year=5, position="소총수", mobilization_status="동원미지정", status="active",
    )
    yesterday = date.today() - timedelta(days=1)
    db.add(person)
    db.add(Education(
        person_id=person.military_number, education_year=5, training_year=yesterday.year,
        scheduled_date=yesterday, training_type="기본훈련", training_round=1,
        attendance_status="참석", training_hours=8,
    ))
    db.commit()

    try:
        add_training_record(
            person.military_number,
            TrainingRecordCreate(
                service_year=5,
                training_year=yesterday.year,
                scheduled_date=yesterday,
                training_type="기본훈련",
                training_round=2,
                attendance_status="무단불참",
                training_hours=0,
            ),
            db,
        )
        assert False, "A satisfied first round cannot advance to round two"
    except HTTPException as error:
        assert error.status_code == 422
    db.close()


def test_patch_requires_current_version_and_audits_before_after() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100305", name="동시 수정", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    yesterday = date.today() - timedelta(days=1)
    record = Education(
        person_id=person.military_number, education_year=1, training_year=yesterday.year,
        scheduled_date=yesterday, training_type="동원훈련Ⅰ형", training_round=1,
        attendance_status="completed", training_hours=28, notes="기존 메모",
    )
    db.add_all([person, record])
    db.commit()
    original_version = record.version

    updated = update_training_record(
        person.military_number,
        record.id,
        TrainingRecordUpdate(expected_version=original_version, notes="수정 메모"),
        db,
        actor="staff-a",
    )
    assert updated.version == original_version + 1

    try:
        update_training_record(
            person.military_number,
            record.id,
            TrainingRecordUpdate(expected_version=original_version, notes="오래된 초안"),
            db,
            actor="staff-b",
        )
        assert False, "Stale patch should be rejected"
    except HTTPException as error:
        assert error.status_code == 409

    audit = db.scalars(select(AuditLog).where(AuditLog.record_id == record.id)).one()
    assert audit.actor_label == "staff-a"
    assert audit.created_at is not None
    assert json.loads(audit.before_data)["notes"] == "기존 메모"
    assert json.loads(audit.after_data)["notes"] == "수정 메모"
    db.close()


def test_officer_type_two_remains_28_hours_after_postponement() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100300",
        name="간부 보충훈련",
        branch="육군",
        rank="하사",
        service_year=1,
        position="분대장",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    first_attempt = Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=1,
        attendance_status="연기",
        training_hours=0,
    )
    db.add(first_attempt)
    db.flush()
    db.add(Postponement(
        person_id=person.military_number,
        type="delay",
        reason="승인된 연기",
        status="approved",
        training_year=2026,
        education_record_id=first_attempt.id,
    ))
    db.commit()

    record = add_training_record(
        person.military_number,
        TrainingRecordCreate(
            service_year=1,
            training_year=(date.today() - timedelta(days=1)).year,
            scheduled_date=date.today() - timedelta(days=1),
            training_type="동원훈련Ⅱ형",
            training_round=2,
            attendance_status="completed",
            training_hours=28,
        ),
        db,
    )

    progress = all_training_progress(db, person)[1]
    assert record.training_hours == 28
    assert progress["target_hours"] == 28
    assert progress["completed_hours"] == 28
    assert progress["remaining_hours"] == 0
    db.close()


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
    db.add(Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2025,
        training_type="동원훈련Ⅰ형",
        attendance_status="completed",
        training_hours=28,
    ))
    db.commit()

    # 1. 2년차에 30시간 추가 시도 -> 초과(28시간)로 인해 400 에러 발생해야 함
    try:
        add_training_record(
            "26-70000010",
            TrainingRecordCreate(
                service_year=2,
                training_year=(date.today() - timedelta(days=1)).year,
                scheduled_date=date.today() - timedelta(days=1),
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
            training_year=(date.today() - timedelta(days=1)).year,
            scheduled_date=date.today() - timedelta(days=1),
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
            TrainingRecordUpdate(expected_version=record.version, training_hours=35),
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
        TrainingRecordUpdate(expected_version=record.version, training_hours=28),
        db,
    )
    assert updated.training_hours == 28

    db.close()


def test_can_record_carryover_hours_during_year_seven() -> None:
    db = make_session()
    person = Person(
        military_number="26-70000011",
        name="이월시험",
        branch="육군",
        rank="병장",
        service_year=7,
        position="소총수",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.add_all([
        Education(person_id=person.military_number, education_year=year, training_year=2020 + year,
                  training_type="동원훈련Ⅱ형", attendance_status="completed", training_hours=32)
        for year in range(1, 5)
    ])
    db.add_all([
        Education(person_id=person.military_number, education_year=7, training_year=2026,
                  training_type="작계훈련(전·후반기)", training_round=1,
                      attendance_status="무단불참", training_hours=0, confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=5, training_year=2025,
                  training_type="기본훈련", attendance_status="completed", training_hours=8),
        Education(person_id=person.military_number, education_year=5, training_year=2025,
                  training_type="작계훈련(전·후반기)", attendance_status="completed", training_hours=12),
        Education(person_id=person.military_number, education_year=6, training_year=2026,
                  training_type="기본훈련", attendance_status="completed", training_hours=8),
        Education(person_id=person.military_number, education_year=6, training_year=2026,
                  training_type="작계훈련(전·후반기)", attendance_status="completed", training_hours=8),
    ])
    db.commit()

    record = add_training_record(
        person.military_number,
        TrainingRecordCreate(
            service_year=7,
            training_year=2026,
            scheduled_date=date.today() - timedelta(days=1),
            training_type="작계훈련(전·후반기)",
            training_round=2,
            attendance_status="completed",
            training_hours=4,
        ),
        db,
    )

    assert record.education_year == 7
    assert record.training_hours == 4
    db.close()
