from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate
from user.app.services.person import create_person
from user.app.services.training import completed_training_hours


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from user.app import models  # noqa: F401

    models.Person.metadata.create_all(engine)
    return Session(engine)


def test_add_new_person_null_previous_hours() -> None:
    db = make_session()
    payload = PersonCreate(
        military_number="24-70000001",
        name="홍길동",
        branch="육군",
        rank="병장",
        unit="100연대",
        position="소총수",
        service_year=2,
        mobilization_status="동원지정",
        previous_training_hours=None,
    )

    person = create_person(db, payload)

    assert person.registration_type == "신규"
    records = db.scalars(select(Education).where(Education.person_id == "24-70000001")).all()
    assert len(records) == 0
    assert completed_training_hours(db, "24-70000001", 2) == 0
    db.close()


def test_add_new_person_zero_previous_hours() -> None:
    db = make_session()
    payload = PersonCreate(
        military_number="24-70000003",
        name="이신규",
        branch="육군",
        rank="상병",
        unit="300연대",
        specialty="3111 101",
        origin_type="병사",
        registration_type=None,
        service_year=1,
        position="소총수",
        mobilization_status="동원지정",
        status="active",
        squad_id=1,
        previous_training_hours=0,
    )

    person = create_person(db, payload)

    assert person.registration_type == "신규"
    records = db.scalars(select(Education).where(Education.person_id == "24-70000003")).all()
    assert len(records) == 0
    db.close()


def test_add_transferred_person_multi_year_allocation() -> None:
    db = make_session()
    # 3년차 동원지정 (1년차 목표 28시간, 2년차 목표 28시간)
    payload = PersonCreate(
        military_number="24-70000004",
        name="박전입",
        branch="육군",
        rank="병장",
        unit="500연대",
        position="소총수",
        service_year=3,
        mobilization_status="동원지정",
        previous_training_hours=50,
    )

    person = create_person(db, payload)

    assert person.registration_type == "예비군 전입"
    records = db.scalars(
        select(Education)
        .where(Education.person_id == "24-70000004")
        .order_by(Education.education_year)
    ).all()

    # 1년차에 28시간, 2년차에 남은 22시간 배정
    assert len(records) == 2
    assert records[0].education_year == 1
    assert records[0].training_hours == 28
    assert records[1].education_year == 2
    assert records[1].training_hours == 22

    assert completed_training_hours(db, "24-70000004", 1) == 28
    assert completed_training_hours(db, "24-70000004", 2) == 22
    assert completed_training_hours(db, "24-70000004", 3) == 0
    db.close()
