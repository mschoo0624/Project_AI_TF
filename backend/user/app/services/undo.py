"""Undo one approved change (편성·재편성·해제) using what AuditLog recorded. """


from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from user.app.models.assignment import Assignment
from user.app.models.audit_log import AuditLog
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.assignment import (
	is_assignable, not_assignable_reason, personnel_category, set_assignment_mobilization_status, squad_capacity,
)
from user.app.services.audit import record_change

UNDOABLE = ("assign", "move", "release")


@dataclass
class UndoStep:
	military_number: str
	name: str
	from_squad_id: int | None  # 지금 있는 분대 (None = 미편성)
	to_squad_id: int | None  # 되돌린 뒤 분대 (None = 해제)


@dataclass
class Skipped:
	military_number: str
	name: str
	reason: str


@dataclass
class UndoPlan:
	changes: list[AuditLog]
	steps: list[UndoStep] = field(default_factory=list)
	skipped: list[Skipped] = field(default_factory=list)


def changes_for(db: Session, trace_id: str) -> list[AuditLog]:
	return list(db.scalars(
		select(AuditLog).where(AuditLog.trace_id == trace_id, AuditLog.action.in_(UNDOABLE))
		.order_by(AuditLog.id)
	).all())


def _items(change: AuditLog) -> list[dict[str, object]]:
	try:
		detail = json.loads(change.detail) if change.detail else []
	except json.JSONDecodeError:
		return []
	return [item for item in detail if isinstance(item, dict) and "military_number" in item] if isinstance(detail, list) else []


def plan_undo(db: Session, trace_id: str, label: Callable[[int], str]) -> UndoPlan:
	"""What undoing this approval would do now. Changes nothing."""
	plan = UndoPlan(changes_for(db, trace_id))
	# 같은 되돌리기 안에서 분대에 다시 넣는 인원도 정원·군별에 센다.
	added: dict[int, list[Person]] = {}
	for change in plan.changes:
		for item in _items(change):
			number = str(item["military_number"])
			person = db.get(Person, number)
			name = str(item.get("name") or number)
			if person is None:
				plan.skipped.append(Skipped(number, name, "인원 정보가 삭제됨"))
				continue
			after = item.get("squad_id") if change.action in ("assign", "move") else None
			if person.squad_id != after:
				now = label(person.squad_id) if person.squad_id is not None else "미편성"
				plan.skipped.append(Skipped(number, person.name, f"이후 다시 바뀜 (지금 {now})"))
				continue
			back = item.get("from_squad_id") if change.action == "move" else item.get("squad_id")
			if change.action == "assign" or back is None:
				# 편성을 되돌리거나, 미편성이던 사람을 옮긴 것을 되돌리면 해제한다.
				plan.steps.append(UndoStep(number, person.name, person.squad_id, None))
				continue
			reason = _cannot_return(db, person, back, added)
			if reason:
				plan.skipped.append(Skipped(number, person.name, reason))
				continue
			added.setdefault(int(back), []).append(person)
			plan.steps.append(UndoStep(number, person.name, person.squad_id, int(back)))
	return plan


def _cannot_return(db: Session, person: Person, squad_id: object, added: dict[int, list[Person]]) -> str | None:
	if not isinstance(squad_id, int):
		return "원래 분대가 기록되지 않음"
	if db.get(Squad, squad_id) is None:
		return "원래 분대가 삭제됨"
	if not is_assignable(person):
		return f"지금은 편성 대상이 아님 ({not_assignable_reason(person)})"
	members = [*db.scalars(select(Person).where(Person.squad_id == squad_id)).all(), *added.get(squad_id, [])]
	if len(members) >= squad_capacity(db, squad_id):
		return "원래 분대 정원이 참"
	group = (person.branch, personnel_category(person.rank))
	if any((member.branch, personnel_category(member.rank)) != group for member in members):
		return "원래 분대에 다른 군별·신분 인원이 있음"
	return None


def apply_undo(db: Session, trace_id: str, label: Callable[[int], str]) -> UndoPlan:
	"""Re-plan on current data and apply it atomically. Raises ValueError when nothing can be undone."""
	plan = plan_undo(db, trace_id, label)
	if not plan.changes:
		raise ValueError("되돌릴 변경 기록이 없습니다.")
	if not plan.steps:
		raise ValueError("되돌릴 수 있는 인원이 없습니다. 모두 이후에 다시 바뀌었거나 원래 분대로 돌아갈 수 없습니다.")
	try:
		for step in plan.steps:
			person = db.get(Person, step.military_number)
			db.execute(delete(Assignment).where(Assignment.person_id == step.military_number))
			person.squad_id = step.to_squad_id
			if step.to_squad_id is not None:
				db.add(Assignment(person_id=step.military_number, squad_id=step.to_squad_id,
					assigned_date=date.today(), status="assigned"))
			set_assignment_mobilization_status(db, person, step.to_squad_id is not None)
		record_change(db, "undo", f"되돌리기 {len(plan.steps)}명 ({', '.join(change.summary or change.action for change in plan.changes)})", [
			{"military_number": step.military_number, "name": step.name,
				"from_squad_id": step.from_squad_id, "squad_id": step.to_squad_id, "reverts": [change.id for change in plan.changes]}
			for step in plan.steps
		])
		db.commit()
	except Exception:
		db.rollback()
		raise
	return plan
