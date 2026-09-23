"""Editable unit hierarchy and scoped, non-destructive vacancy filling."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from user.app.models.assignment import Assignment
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.assignment import (
    POSITION_SPECIALTIES, personnel_category, rank_candidates_for_position,
    set_assignment_mobilization_status,
)

KINDS = {"root", "company", "platoon", "squad"}
ALLOWED_CHILDREN = {
    "root": {"company", "platoon", "squad"},
    "company": {"platoon", "squad"},
    "platoon": {"squad"},
    "squad": set(),
}


def _nodes(db: Session) -> dict[int, OrganizationNode]:
    return {node.id: node for node in db.scalars(select(OrganizationNode).order_by(OrganizationNode.id)).all()}


def _descendants(nodes: dict[int, OrganizationNode], node_id: int) -> list[OrganizationNode]:
    result: list[OrganizationNode] = []
    def visit(current: int) -> None:
        for node in nodes.values():
            if node.parent_id == current:
                result.append(node)
                visit(node.id)
    visit(node_id)
    return result


def _get(nodes: dict[int, OrganizationNode], node_id: int) -> OrganizationNode:
    node = nodes.get(node_id)
    if node is None:
        raise ValueError("선택한 편제 단위가 없습니다.")
    return node


def release_members(db: Session, selected_id: int, person_id: str | None = None) -> dict[str, int]:
    """Release current members only within the selected unit and its descendants."""
    nodes = _nodes(db)
    selected = _get(nodes, selected_id)
    squad_ids = [node.squad_id for node in [selected, *_descendants(nodes, selected_id)]
                 if node.squad_id is not None]
    query = select(Person).where(Person.squad_id.in_(squad_ids))
    if person_id is not None:
        query = query.where(Person.military_number == person_id)
    try:
        people = list(db.scalars(query).all())
        if person_id is not None and not people:
            raise ValueError("선택한 부대에 편성된 인원이 아닙니다.")
        for person in people:
            db.execute(delete(Assignment).where(
                Assignment.person_id == person.military_number,
                Assignment.squad_id == person.squad_id,
            ))
            person.squad_id = None
            set_assignment_mobilization_status(db, person, False)
        db.commit()
        return {"released_count": len(people)}
    except Exception:
        db.rollback()
        raise


def hierarchy(db: Session) -> list[dict[str, object]]:
    """Flat tree records; aggregate actual memberships without assuming unknown quotas."""
    nodes = _nodes(db)
    all_people = db.scalars(select(Person)).all()
    counts: dict[int, int] = {}
    for person in all_people:
        if person.squad_id is not None:
            counts[person.squad_id] = counts.get(person.squad_id, 0) + 1

    def squad_ids(node: OrganizationNode) -> list[int]:
        return ([node.squad_id] if node.squad_id is not None else []) + [
            child.squad_id for child in _descendants(nodes, node.id) if child.squad_id is not None
        ]

    results: list[dict[str, object]] = []
    for node in nodes.values():
        members = squad_ids(node)
        total = sum(counts.get(sid, 0) for sid in members)
        squads = [unit for unit in [node, *_descendants(nodes, node.id)]
                  if unit.kind == "squad" and unit.squad_id is not None]
        planned: int | None = sum(unit.planned_strength or 11 for unit in squads) if squads else None
        # Overfill in one squad must not hide a vacancy in a different squad.
        planned_actual: int | None = sum(min(counts.get(unit.squad_id, 0), unit.planned_strength or 11)
                                         for unit in squads) if squads else None
        shortage: int | None = sum(max(0, (unit.planned_strength or 11) - counts.get(unit.squad_id, 0))
                                   for unit in squads) if squads else None
        results.append({
            "id": node.id, "parent_id": node.parent_id, "kind": node.kind,
            "name": node.name,
            "squad_id": node.squad_id, "person_count": total,
            "planned_strength": planned, "planned_actual": planned_actual, "shortfall": shortage,
        })
    return results


def create_unit(db: Session, parent_id: int, kind: str, name: str) -> OrganizationNode:
    nodes = _nodes(db)
    parent = _get(nodes, parent_id)
    name = name.strip()
    if kind not in KINDS or kind not in ALLOWED_CHILDREN[parent.kind]:
        raise ValueError("이 위치에 해당 편제 단위를 추가할 수 없습니다.")
    if not name or len(name) > 100:
        raise ValueError("이름은 1~100자여야 합니다.")
    try:
        squad_id: int | None = None
        if kind == "squad":
            squad = Squad(name=name)
            db.add(squad)
            db.flush()
            squad_id = squad.id
        node = OrganizationNode(parent_id=parent_id, kind=kind, name=name,
                                squad_id=squad_id, planned_strength=11 if kind == "squad" else None)
        db.add(node)
        db.commit()
        db.refresh(node)
        return node
    except Exception:
        db.rollback()
        raise


def rename_unit(db: Session, node_id: int, name: str) -> None:
    node = _get(_nodes(db), node_id)
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("이름은 1~100자여야 합니다.")
    try:
        node.name = name
        if node.squad_id is not None:
            squad = db.get(Squad, node.squad_id)
            if squad is not None:
                squad.name = name
        db.commit()
    except Exception:
        db.rollback()
        raise


def move_unit(db: Session, node_id: int, parent_id: int) -> None:
    nodes = _nodes(db)
    node, parent = _get(nodes, node_id), _get(nodes, parent_id)
    if parent_id == node_id or parent_id in {child.id for child in _descendants(nodes, node_id)}:
        raise ValueError("편제 단위를 자기 자신 또는 하위 단위로 이동할 수 없습니다.")
    if node.kind == "root" or node.kind not in ALLOWED_CHILDREN[parent.kind]:
        raise ValueError("해당 편제 단위를 이 위치로 이동할 수 없습니다.")
    try:
        node.parent_id = parent_id
        db.commit()
    except Exception:
        db.rollback()
        raise


def delete_unit(db: Session, node_id: int) -> None:
    nodes = _nodes(db)
    node = _get(nodes, node_id)
    if node.kind == "root":
        raise ValueError("최상위 편제는 삭제할 수 없습니다.")
    if any(child.parent_id == node_id for child in nodes.values()):
        raise ValueError("하위 단위를 먼저 다른 편제로 이동하거나 삭제하세요.")
    if node.squad_id is not None:
        if db.scalar(select(Person.military_number).where(Person.squad_id == node.squad_id).limit(1)):
            raise ValueError("인원이 배정된 분대는 삭제할 수 없습니다.")
        if db.scalar(select(Assignment.id).where(Assignment.squad_id == node.squad_id).limit(1)):
            raise ValueError("배정 이력이 있는 분대는 삭제할 수 없습니다.")
    try:
        if node.squad_id is not None:
            squad = db.get(Squad, node.squad_id)
            db.delete(node)
            db.flush()
            if squad is not None:
                db.delete(squad)
        else:
            db.delete(node)
        db.commit()
    except Exception:
        db.rollback()
        raise

def assign_vacancies(db: Session, selected_id: int) -> dict[str, object]:
    """Fill vacancies in existing squads without changing the hierarchy."""
    nodes = _nodes(db)
    selected = _get(nodes, selected_id)
    target_squads = [node for node in [selected, *_descendants(nodes, selected_id)]
                     if node.kind == "squad" and node.squad_id is not None]
    if not target_squads:
        raise ValueError("선택한 단위에 분대가 없습니다. 분대를 추가하세요.")

    members = db.scalars(select(Person)).all()
    squad_members: dict[int, list[Person]] = {}
    for person in members:
        if person.squad_id is not None:
            squad_members.setdefault(person.squad_id, []).append(person)

    position_order = {position: index for index, position in enumerate(POSITION_SPECIALTIES)}
    available = [person for person in members if person.squad_id is None
                 and person.status == "active" and person.service_year is not None]
    ordered: list[Person] = []
    for position in sorted({person.position or "" for person in available},
                           key=lambda p: (position_order.get(p, len(position_order)), p)):
        ordered.extend(candidate.person for candidate in rank_candidates_for_position(
            [person for person in available if (person.position or "") == position], position))

    used: set[str] = set()
    assignments: list[dict[str, object]] = []
    try:
        for node in target_squads:
            squad_id = node.squad_id
            current = squad_members.setdefault(squad_id, [])
            remaining = max(0, (node.planned_strength or 11) - len(current))
            for _ in range(remaining):
                existing_groups = {(person.branch, personnel_category(person.rank))
                                   for person in current}
                candidate = next((person for person in ordered if person.military_number not in used
                                  and (not existing_groups or existing_groups == {
                                      (person.branch, personnel_category(person.rank))})), None)
                if candidate is None:
                    break
                candidate.squad_id = squad_id
                set_assignment_mobilization_status(db, candidate, True)
                db.add(Assignment(person_id=candidate.military_number, squad_id=squad_id,
                                  assigned_date=date.today(), status="assigned"))
                current.append(candidate)
                used.add(candidate.military_number)
                assignments.append({"military_number": candidate.military_number,
                                    "name": candidate.name, "squad_id": squad_id})
        shortfall = sum(max(0, (node.planned_strength or 11) - len(squad_members[node.squad_id]))
                        for node in target_squads)
        db.commit()
        return {"total_assigned": len(assignments), "total_shortfall": shortfall,
                "assigned": assignments, "scope_id": selected_id}
    except Exception:
        db.rollback()
        raise


def expand_formation(db: Session, selected_id: int) -> dict[str, object]:
    """Create the standard 10-platoon, 4-squad formation without assigning people."""
    nodes = _nodes(db)
    selected = _get(nodes, selected_id)
    if selected.kind != "root":
        raise ValueError("소대와 분대 확장은 최상위 편제에서만 실행할 수 있습니다.")

    created_platoons: list[dict[str, object]] = []
    created_squads: list[dict[str, object]] = []
    try:
        platoons = [node for node in nodes.values()
                    if node.parent_id == selected.id and node.kind == "platoon"]
        platoon_number = 1
        while len(platoons) < 10:
            names = {node.name for node in nodes.values() if node.parent_id == selected.id}
            while f"{platoon_number}소대" in names:
                platoon_number += 1
            platoon = OrganizationNode(parent_id=selected.id, kind="platoon",
                                       name=f"{platoon_number}소대")
            db.add(platoon)
            db.flush()
            nodes[platoon.id] = platoon
            platoons.append(platoon)
            created_platoons.append({"id": platoon.id, "name": platoon.name})
            platoon_number += 1

        for platoon in platoons:
            squads = [node for node in nodes.values()
                      if node.parent_id == platoon.id and node.kind == "squad"]
            squad_number = 1
            while len(squads) < 4:
                names = {node.name for node in nodes.values() if node.parent_id == platoon.id}
                while f"{squad_number}분대" in names:
                    squad_number += 1
                squad = Squad(name=f"{squad_number}분대", description="기본 편제")
                db.add(squad)
                db.flush()
                node = OrganizationNode(parent_id=platoon.id, kind="squad", name=squad.name,
                                        squad_id=squad.id, planned_strength=11)
                db.add(node)
                db.flush()
                nodes[node.id] = node
                squads.append(node)
                created_squads.append({"id": node.id, "squad_id": squad.id, "name": node.name})
                squad_number += 1
        db.commit()
        return {"created_platoons": created_platoons, "created_squads": created_squads,
                "total_platoons": len(platoons), "total_squads": sum(
                    1 for node in nodes.values() if node.kind == "squad"
                )}
    except Exception:
        db.rollback()
        raise
