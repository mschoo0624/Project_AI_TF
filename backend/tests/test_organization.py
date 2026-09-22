"""Regression coverage for persistent hierarchy and non-destructive scoped filling."""
from __future__ import annotations

from sqlalchemy import create_engine, func, select, text
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app.database import Base, _ensure_squad_based_hierarchy
from user.app.models.assignment import Assignment
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.organization import (
    assign_vacancies, create_unit, delete_unit, expand_formation, hierarchy, move_unit,
)


def make_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from user.app import models  # noqa: F401
    Base.metadata.create_all(engine)
    return Session(engine)


def add_person(db: Session, number: str, squad_id: int | None = None, branch: str = "육군") -> None:
    db.add(Person(military_number=number, name=number, branch=branch, rank="병장",
                  specialty="3111101", position="행정병", service_year=1,
                  status="active", squad_id=squad_id))


def test_hierarchy_create_move_and_guard_delete() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="편제")
    db.add(root)
    db.commit()
    company = create_unit(db, root.id, "company", "가중대")
    platoon = create_unit(db, company.id, "platoon", "가소대")
    squad_node = create_unit(db, platoon.id, "squad", "1분대")
    assert platoon.planned_strength is None
    assert squad_node.planned_strength == 11
    assert squad_node.squad_id is not None
    assert db.get(Squad, squad_node.squad_id).name == "1분대"
    with pytest.raises(ValueError, match="하위 단위"):
        delete_unit(db, platoon.id)
    with pytest.raises(ValueError, match="자기 자신"):
        move_unit(db, company.id, platoon.id)
    move_unit(db, squad_node.id, root.id)
    delete_unit(db, platoon.id)
    db.close()


def test_deleting_squad_removes_linked_squad_record() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="편제")
    db.add(root)
    db.commit()
    squad_node = create_unit(db, root.id, "squad", "삭제 대상 분대")
    squad_id = squad_node.squad_id

    delete_unit(db, squad_node.id)

    assert db.get(OrganizationNode, squad_node.id) is None
    assert db.get(Squad, squad_id) is None
    db.close()


def test_scoped_auto_fills_only_shortfall_and_keeps_other_assignments() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="편제")
    db.add(root)
    db.flush()
    platoon_a = create_unit(db, root.id, "platoon", "1소대")
    platoon_b = create_unit(db, root.id, "platoon", "2소대")
    squad_a = create_unit(db, platoon_a.id, "squad", "1분대")
    squad_b = create_unit(db, platoon_b.id, "squad", "2분대")
    assert squad_a.squad_id and squad_b.squad_id
    for n in range(9):
        add_person(db, f"a{n:02d}", squad_a.squad_id)
    add_person(db, "preserved", squad_b.squad_id)
    for n in range(5):
        add_person(db, f"available{n:02d}")
    db.commit()

    result = assign_vacancies(db, platoon_a.id)
    assert result["total_assigned"] == 2
    assert result["total_shortfall"] == 0
    assert db.get(Person, "preserved").squad_id == squad_b.squad_id
    assert db.scalar(select(Person).where(Person.squad_id == squad_a.squad_id).with_only_columns(func.count())) == 11
    assert db.scalar(select(Person).where(Person.squad_id == squad_b.squad_id).with_only_columns(func.count())) == 1
    assert assign_vacancies(db, platoon_a.id)["total_assigned"] == 0
    assert len(db.scalars(select(Assignment)).all()) == 2
    tree = hierarchy(db)
    assert next(node for node in tree if node["id"] == platoon_a.id)["person_count"] == 11
    assert next(node for node in tree if node["id"] == root.id)["planned_strength"] == 22
    db.close()


def test_unplanned_squad_uses_squad_quota_and_preserves_assignments() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="편제")
    squad = Squad(name="기존 분대")
    db.add_all([root, squad])
    db.flush()
    node = OrganizationNode(kind="squad", name="기존 분대", parent_id=root.id, squad_id=squad.id)
    db.add(node)
    add_person(db, "assigned", squad.id)
    add_person(db, "available")
    db.commit()
    result = assign_vacancies(db, node.id)
    assert result["total_assigned"] == 1
    assert result["total_shortfall"] == 9
    assert db.get(Person, "assigned").squad_id == squad.id
    assert db.get(Person, "available").squad_id == squad.id
    db.close()


def test_shared_platoon_cap_for_two_squads_and_group_integrity() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="편제")
    db.add(root)
    db.commit()
    platoon = create_unit(db, root.id, "platoon", "1소대")
    squad_a = create_unit(db, platoon.id, "squad", "1분대")
    squad_b = create_unit(db, platoon.id, "squad", "2분대")
    for n in range(10):
        add_person(db, f"existing{n:02d}", squad_b.squad_id)
    add_person(db, "eligible", branch="육군")
    add_person(db, "other_branch", branch="해군")
    db.commit()
    result = assign_vacancies(db, squad_a.id)
    assert result["total_assigned"] == 1
    assert db.get(Person, "eligible").squad_id == squad_a.squad_id
    assert db.get(Person, "other_branch").squad_id is None
    assert len([p for p in db.scalars(select(Person)).all() if p.squad_id is not None]) == 11
    assert result["total_shortfall"] == 10
    db.close()


def test_legacy_group_removed_and_squad_totals_recalculated() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="삼각동대")
    db.add(root)
    db.flush()
    parked = OrganizationNode(kind="company", name="기존 분대 (미배치)", parent_id=root.id)
    db.add(parked)
    db.flush()
    for number in range(1, 21):
        legacy = Squad(name=f"{number}분대", description=f"제{number}분대")
        db.add(legacy)
        db.flush()
        db.add(OrganizationNode(kind="squad", name=legacy.name, parent_id=parked.id,
                                squad_id=legacy.id))
    db.flush()
    add_person(db, "old-member", 1)
    db.add(Assignment(person_id="old-member", squad_id=1, assigned_date=__import__("datetime").date.today(), status="assigned"))
    for pnum in range(1, 4):
        platoon = OrganizationNode(kind="platoon", parent_id=root.id, name=f"{pnum}소대", planned_strength=11)
        db.add(platoon)
        db.flush()
        for snum in range(1, 5):
            squad = Squad(name=f"{pnum}소대 {snum}분대", description="시연용 편제: 기존 인원 미이동")
            db.add(squad)
            db.flush()
            db.add(OrganizationNode(kind="squad", parent_id=platoon.id,
                                    name=f"{snum}분대", squad_id=squad.id))
    db.commit()
    engine = db.get_bind()
    db.close()
    with engine.begin() as connection:
        _ensure_squad_based_hierarchy(connection)
    with Session(engine) as check:
        tree = hierarchy(check)
        assert len(tree) == 16  # root + three platoons + twelve squads
        assert {n["planned_strength"] for n in tree if n["kind"] == "squad"} == {11}
        assert {n["planned_strength"] for n in tree if n["kind"] == "platoon"} == {44}
        assert next(n for n in tree if n["kind"] == "root")["planned_strength"] == 132
        assert check.scalar(select(func.count()).select_from(Squad)) == 12
        assert check.get(Person, "old-member") is not None
        assert check.get(Person, "old-member").squad_id is None
        assert check.scalar(select(func.count()).select_from(Assignment)) == 0
    with engine.begin() as connection:
        _ensure_squad_based_hierarchy(connection)
    with Session(engine) as check:
        assert len(hierarchy(check)) == 16  # restart does not recreate deleted units
        platoon = check.scalar(select(OrganizationNode).where(OrganizationNode.kind == "platoon"))
        new_squad = create_unit(check, platoon.id, "squad", "5분대")
        assert next(n for n in hierarchy(check) if n["id"] == platoon.id)["planned_strength"] == 55
        assert next(n for n in hierarchy(check) if n["kind"] == "root")["planned_strength"] == 143
        delete_unit(check, new_squad.id)
        assert next(n for n in hierarchy(check) if n["kind"] == "root")["planned_strength"] == 132


def test_scoped_auto_fill_four_squads_with_eleven_each() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="삼각동대")
    db.add(root)
    db.flush()
    platoon = create_unit(db, root.id, "platoon", "1소대")
    squads = [create_unit(db, platoon.id, "squad", f"{i}분대") for i in range(1, 5)]
    add_person(db, "preserved", squads[0].squad_id)
    for i in range(50):
        add_person(db, f"available-{i:03}")
    db.commit()
    first = assign_vacancies(db, squads[0].id)
    assert first["total_assigned"] == 10
    assert first["total_shortfall"] == 0
    all_result = assign_vacancies(db, platoon.id)
    assert all_result["total_assigned"] == 33
    assert all_result["total_shortfall"] == 0
    assert [n["person_count"] for n in hierarchy(db) if n["kind"] == "squad"] == [11] * 4
    assert next(n for n in hierarchy(db) if n["kind"] == "platoon")["planned_strength"] == 44
    assert assign_vacancies(db, root.id)["total_assigned"] == 0
    db.close()


def test_expand_formation_is_separate_from_auto_fill() -> None:
    db = make_session()
    root = OrganizationNode(kind="root", name="삼각동대")
    db.add(root)
    db.flush()
    create_unit(db, root.id, "platoon", "1소대")
    db.commit()

    result = expand_formation(db, root.id)

    assert result["total_platoons"] == 10
    assert result["total_squads"] == 40
    assert len(result["created_platoons"]) == 9
    assert len(result["created_squads"]) == 40
    assert len([node for node in hierarchy(db) if node["kind"] == "platoon"]) == 10
    assert len([node for node in hierarchy(db) if node["kind"] == "squad"]) == 40
    db.close()
