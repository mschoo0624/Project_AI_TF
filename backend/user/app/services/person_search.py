"""Structured member search shared by the roster API and the Copilot."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.squad import Squad
from user.app.services.assignment import NCO_RANKS, OFFICER_RANKS, SOLDIER_RANKS

# 간부 = 부사관 + 장교
CATEGORY_RANKS: dict[str, set[str]] = {
	"병사": SOLDIER_RANKS,
	"부사관": NCO_RANKS,
	"장교": OFFICER_RANKS,
	"간부": NCO_RANKS | OFFICER_RANKS,
}


@dataclass(frozen=True)
class PersonSearch:
	query_text: str | None = None
	branch: str | None = None
	rank: str | None = None
	status: str | None = None
	mobilization_status: str | None = None
	platoon: str | None = None
	category: str | None = None
	assigned: bool | None = None
	registration_type: str | None = None


def squad_ids_for_platoon(db: Session, platoon: str) -> list[int]:
	"""Squads under the named platoon in the organization tree, or named "<platoon> N분대"."""
	platoon_ids = select(OrganizationNode.id).where(
		OrganizationNode.kind == "platoon", OrganizationNode.name == platoon
	)
	ids = set(db.scalars(
		select(OrganizationNode.squad_id).where(
			OrganizationNode.parent_id.in_(platoon_ids),
			OrganizationNode.squad_id.is_not(None),
		)
	).all())
	ids.update(db.scalars(select(Squad.id).where(Squad.name.like(f"{platoon} %"))).all())
	return sorted(ids)


def search_people(db: Session, search: PersonSearch) -> list[Person]:
	query = select(Person)
	if search.query_text:
		pattern = f"%{search.query_text}%"
		query = query.where(or_(Person.name.like(pattern), Person.military_number.like(pattern)))
	if search.branch:
		query = query.where(Person.branch == search.branch)
	if search.rank:
		query = query.where(Person.rank == search.rank)
	if search.status:
		query = query.where(Person.status == search.status)
	if search.mobilization_status:
		query = query.where(Person.mobilization_status == search.mobilization_status)
	if search.category:
		if search.category not in CATEGORY_RANKS:
			raise ValueError(f"Unknown personnel category: {search.category}")
		query = query.where(Person.rank.in_(CATEGORY_RANKS[search.category]))
	if search.platoon:
		query = query.where(Person.squad_id.in_(squad_ids_for_platoon(db, search.platoon)))
	if search.registration_type:
		query = query.where(Person.registration_type == search.registration_type)
	if search.assigned is True:
		query = query.where(Person.squad_id.is_not(None))
	elif search.assigned is False:
		query = query.where(Person.squad_id.is_(None))
	return list(db.scalars(query.order_by(Person.military_number)).all())
