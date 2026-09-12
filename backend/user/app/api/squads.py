"""Squad API routes."""
"""
기능 설명:

전체 분대 목록 조회
분대별 인원 수 표시
특정 분대의 소속 인원 조회
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from user.app.database import get_db
from user.app.models.squad import Squad
from user.app.schemas.assignment import AssignmentPlan
from user.app.services.assignment import available_assignment_candidates, fill_squad_positions

router = APIRouter(prefix="/squads", tags=["squads"])


@router.post("/{squad_id}/fill-positions")
def fill_positions(
	squad_id: int,
	plan: AssignmentPlan,
	db: Session = Depends(get_db),
) -> dict[str, object]:
	try:
		return fill_squad_positions(
			db,
			squad_id,
			plan.position_quotas,
			tuple(plan.branch_order),
			plan.allow_branch_merge,
		)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/assignment-candidates")
def assignment_candidates(
	position: str | None = None,
	db: Session = Depends(get_db),
) -> dict[str, dict[str, list[dict[str, object]]]]:
	return available_assignment_candidates(db, position)

@router.get("")
def list_squads(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	squads = db.scalars(
		select(Squad).options(selectinload(Squad.persons)).order_by(Squad.id)
	).all()
	return [
		{
			"id": squad.id,
			"name": squad.name,
			"description": squad.description,
			"person_count": len(squad.persons),
		}
		for squad in squads
	]

@router.get("/{squad_id}")
def get_squad(squad_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
	squad = db.scalar(
		select(Squad)
		.options(selectinload(Squad.persons))
		.where(Squad.id == squad_id)
	)
	if squad is None:
		raise HTTPException(status_code=404, detail="Squad not found")

	return {
		"id": squad.id,
		"name": squad.name,
		"description": squad.description,
		"persons": squad.persons,
	}
