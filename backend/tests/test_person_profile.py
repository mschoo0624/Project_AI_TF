from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from user.app import models  # noqa: F401
from user.app.database import Base
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.models.assignment import Assignment
from user.app.models.education import Education
from user.app.models.annual_status import AnnualStatus
from user.app.models.postpoment import Postponement
from user.app.schemas.person import PersonProfileUpdate
from user.app.services.person_profile import ProfileError, save_profile


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(text("PRAGMA foreign_keys=ON"))
        session.add(Squad(id=1, name="1분대"))
        session.flush()
        session.add(Person(military_number="26-100", name="테스트", branch="육군", rank="병장",
                           service_year=2, position="행정병", specialty="3111101", status="active",
                           mobilization_status="동원지정", squad_id=1))
        session.commit()
        yield session


def draft(**changes):
    return dict(name="수정 이름", military_number="26-100", unit="삼각동대", branch="육군",
                status="active", mobilization_status="동원지정", position="행정병", specialty="3111 101") | changes


@pytest.mark.parametrize("changes,field", [
    ({"name": " "}, "name"), ({"military_number": ""}, "military_number"),
    ({"specialty": "999999"}, "specialty"), ({"position": "통신병"}, "position"),
    ({"branch": "기타군"}, "branch"), ({"mobilization_status": "해당없음"}, "mobilization_status"),
])
def test_invalid_fields_do_not_save(db, changes, field):
    person = db.get(Person, "26-100")
    with pytest.raises(ProfileError) as error:
        save_profile(db, person, draft(**changes))
    assert field in error.value.fields
    assert person.name == "테스트"


def test_duplicate_number(db):
    db.add(Person(military_number="26-200", name="다른 사람", branch="육군", service_year=0))
    db.commit()
    with pytest.raises(ProfileError) as error:
        save_profile(db, db.get(Person, "26-100"), draft(military_number="26-200"))
    assert "military_number" in error.value.fields


@pytest.mark.parametrize("field,value", [("rank", "하사"), ("service_year", 3), ("squad_id", None)])
def test_locked_fields_are_rejected(field, value):
    with pytest.raises(ValidationError):
        PersonProfileUpdate(**(draft() | {field: value}))


def test_number_change_preserves_all_related_records(db):
    db.add_all([
        AnnualStatus(person_id="26-100", service_year=1, mobilization_status="동원지정"),
        Assignment(person_id="26-100", squad_id=1, assigned_date=date.today()),
        Education(person_id="26-100", education_year=1, training_hours=28),
        Postponement(person_id="26-100", reason="사유"),
    ])
    db.commit()
    result = save_profile(db, db.get(Person, "26-100"), draft(military_number="26-101", mobilization_status="학생예비군"))
    assert result.name == "수정 이름"
    assert result.specialty == "3111101"
    assert (result.squad_id, result.rank, result.service_year) == (1, "병장", 2)
    assert db.get(Person, "26-100") is None
    for model in (AnnualStatus, Assignment, Education, Postponement):
        assert all(row.person_id == "26-101" for row in db.scalars(select(model)))
    assert db.get(AnnualStatus, ("26-101", 1)).mobilization_status == "동원지정"
    assert db.get(AnnualStatus, ("26-101", 2)).mobilization_status == "학생예비군"
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_shared_specialty_allows_both_registered_positions(db):
    result = save_profile(db, db.get(Person, "26-100"), draft(specialty="231101", position="운전병"))
    assert result.position == "운전병"
    result = save_profile(db, result, draft(specialty="231101", position="보급병"))
    assert result.position == "보급병"
