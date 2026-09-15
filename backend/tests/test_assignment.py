from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.models.assignment import Assignment
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.assignment import (
    confirm_assignment_selections,
    fill_squad_positions,
    rank_candidates_for_position,
    recommend_squads_for_person,
    suggest_position_for_specialty,
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


def add_person(
    db: Session,
    military_number: str,
    position: str,
    specialty: str | None,
    service_year: int = 5,
    squad_id: int | None = None,
) -> Person:
    person = Person(
        military_number=military_number,
        name=military_number,
        branch="육군",
        rank="하사",
        specialty=specialty,
        service_year=service_year,
        position=position,
        mobilization_status="해당없음",
        status="active",
        squad_id=squad_id,
    )
    db.add(person)
    return person


def test_fill_squad_positions_consumes_pool_and_reports_shortfall() -> None:
    db = make_session()
    db.add_all([
        Squad(id=1, name="편성 대상", description="test"),
        Squad(id=2, name="기존 분대", description="test"),
    ])
    add_person(db, "exact-admin", "행정병", "3111 101", service_year=5)
    add_person(db, "fallback-admin", "행정병", "999 999", service_year=6)
    add_person(db, "other-admin", "행정병", None, service_year=5)
    add_person(db, "assigned-admin", "행정병", "3111 101", service_year=6, squad_id=2)
    add_person(db, "signal", "통신병", "171 101", service_year=5)
    db.commit()

    result = fill_squad_positions(
        db,
        1,
        {"행정병": 2, "통신병": 2},
    )

    assert result["positions"]["행정병"]["assigned"] == [
        {"military_number": "exact-admin", "name": "exact-admin"},
        {"military_number": "fallback-admin", "name": "fallback-admin"},
    ]
    assert result["positions"]["행정병"]["shortfall"] == 0
    assert result["positions"]["통신병"]["shortfall"] == 1
    assert result["total_assigned"] == 3
    assert result["total_shortfall"] == 1

    assigned = db.scalars(select(Assignment).order_by(Assignment.id)).all()
    assert [item.person_id for item in assigned] == [
        "exact-admin",
        "fallback-admin",
        "signal",
    ]
    assert len({item.person_id for item in assigned}) == len(assigned)
    assert db.get(Person, "assigned-admin").squad_id == 2
    assert db.get(Person, "exact-admin").squad_id == 1
    assert all(item.assigned_date == date.today() for item in assigned)
    db.close()


def test_fill_squad_positions_uses_fixed_input_order() -> None:
    db = make_session()
    db.add(Squad(id=1, name="편성 대상", description="test"))
    add_person(db, "admin", "행정병", "3111 101")
    add_person(db, "signal", "통신병", "171 101")
    db.commit()

    result = fill_squad_positions(db, 1, {"통신병": 1, "행정병": 1})

    assert list(result["positions"]) == ["통신병", "행정병"]
    assert [item.person_id for item in db.scalars(select(Assignment).order_by(Assignment.id))] == [
        "signal",
        "admin",
    ]
    db.close()


def test_suggest_position_for_specialty_accepts_readable_name_and_code() -> None:
    assert suggest_position_for_specialty("통신") == "통신병"
    assert suggest_position_for_specialty("의무") == "의무병"
    assert suggest_position_for_specialty("3111 101") == "행정병"
    assert suggest_position_for_specialty("171101") == "통신병"
    assert suggest_position_for_specialty("기타") is None


def test_confirm_assignment_selections_persists_reviewed_squad_choice() -> None:
    db = make_session()
    db.add_all([Squad(id=1, name="1분대"), Squad(id=2, name="2분대")])
    add_person(db, "reviewed", "행정병", "3111 101")
    db.commit()

    result = confirm_assignment_selections(db, [("reviewed", 2)])

    assert result["total_assigned"] == 1
    assert db.get(Person, "reviewed").squad_id == 2
    assert db.scalars(select(Assignment)).one().squad_id == 2
    db.close()


def test_rank_candidates_prioritizes_soldier_year_and_public_health_medic() -> None:
    db = make_session()
    older_soldier = add_person(db, "older-soldier", "행정병", "3111 101", service_year=4)
    priority_soldier = add_person(db, "priority-soldier", "행정병", "999 999", service_year=5)
    older_soldier.rank = "병장"
    priority_soldier.rank = "병장"
    medic = add_person(db, "medic", "의무병", "411 101", service_year=5)
    medic.origin_type = "공중보건의출신"
    other_medic = add_person(db, "other-medic", "의무병", "411 101", service_year=5)
    db.commit()

    admin_ranked = rank_candidates_for_position([older_soldier, priority_soldier], "행정병")
    medic_ranked = rank_candidates_for_position([other_medic, medic], "의무병")

    assert admin_ranked[0].person.military_number == "priority-soldier"
    assert medic_ranked[0].person.military_number == "medic"
    db.close()


def test_confirm_rejects_mixed_branch_or_personnel_category_squad() -> None:
    db = make_session()
    db.add(Squad(id=1, name="육군 병사 분대"))
    first = add_person(db, "first", "행정병", "3111 101")
    first.rank = "병장"
    db.commit()
    confirm_assignment_selections(db, [("first", 1)])
    second = add_person(db, "second", "행정병", "3111 101")
    second.branch = "해군"
    db.commit()

    try:
        confirm_assignment_selections(db, [("second", 1)])
        raise AssertionError("mixed squad assignment should fail")
    except ValueError as error:
        assert "cannot mix" in str(error)
    db.close()


def test_recommend_squads_returns_only_compatible_top_three() -> None:
    db = make_session()
    db.add_all([Squad(id=1, name="육군 병사 1"), Squad(id=2, name="해군 병사 1"), Squad(id=3, name="육군 병사 2"), Squad(id=4, name="육군 병사 3")])
    new_person = add_person(db, "new-person", "행정병", "3111 101")
    new_person.rank = "병장"
    member = add_person(db, "member", "통신병", "171 101", squad_id=1)
    member.rank = "병장"
    member.branch = "육군"
    other = add_person(db, "other", "행정병", "3111 101", squad_id=2)
    other.rank = "병장"
    other.branch = "해군"
    db.commit()

    recommendations = recommend_squads_for_person(db, "new-person")

    assert [item["squad_id"] for item in recommendations] == [3, 4, 1]
    db.close()
