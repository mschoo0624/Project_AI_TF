"""Dashboard API routes."""
"""
반환하는 통계:

전체 인원 수
현재 활성 인원 수
대기 중인 연기 신청 수
군종별 인원 수
계급별 인원 수
분대별 인원 수
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.squad import Squad

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def grouped_counts(db: Session, field: object) -> dict[str, int]:
	rows = db.execute(select(field, func.count()).group_by(field)).all()
	return {str(key): count for key, count in rows if key is not None}


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, object]:
	total_people = db.scalar(select(func.count()).select_from(Person)) or 0
	active_people = db.scalar(
		select(func.count()).select_from(Person).where(Person.status == "active")
	) or 0

	squad_counts = dict(
		db.execute(
			select(Squad.name, func.count(Person.military_number))
			.outerjoin(Person, Person.squad_id == Squad.id)
			.group_by(Squad.id, Squad.name)
			.order_by(Squad.id)
		).all()
	)

	return {
		"total_people": total_people,
		"active_people": active_people,
		"by_branch": grouped_counts(db, Person.branch),
		"by_rank": grouped_counts(db, Person.rank),
		"by_squad": squad_counts,
	}
