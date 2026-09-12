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

router = APIRouter(prefix="/squads", tags=["squads"])

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
