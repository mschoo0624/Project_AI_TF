"""Reservist API routes."""
# 예비군 인원 관리 API입니다.
"""
기능 설명:

전체 인원 조회
군번으로 특정 인원 조회
인원 등록
인원 정보 수정
인원 삭제
군종, 계급, 상태로 필터링
"""

from typing import Literal
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.annual_status import AnnualStatus
from user.app.models.assignment import Assignment
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.user import User
from user.app.models.training_recalculation import (
	TrainingCarryover,
	TrainingCarryoverResolution,
	TrainingYearResult,
)
from user.app.schemas.person import (
	PersonCreate,
	PersonRead,
	PersonRosterRead,
	PersonUpdate,
	PersonProfileUpdate,
)
from user.app.services.person_profile import ProfileError, profile_options, save_profile
from user.app.services.assignment import grouped_candidates, is_assignable, not_assignable_reason
from user.app.services.person import create_person
from user.app.services.person_search import PersonSearch, search_people
from user.app.services.training import (
	OVERDUE_GRACE_DAYS,
	ROUND_SCHEDULED,
	training_last_session_days,
	ROUND_POSTPONED,
	UNEXCUSED_ABSENCE,
	_approved_excusal_record_ids,
	all_training_progress,
	apply_mobilization_status_change,
)
from user.app.services.auth import require_scheduler, require_viewer
from user.app.services.training_recalculation import recalculate_person

router = APIRouter(prefix="/reservists", tags=["reservists"])
persons_router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("/prosecution-targets", dependencies=[Depends(require_viewer)])
def list_prosecution_targets(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	"""List reservists currently marked as prosecution targets by training rules."""
	people = db.scalars(select(Person).order_by(Person.military_number)).all()
	result: list[dict[str, object]] = []
	for person in people:
		progress = all_training_progress(db, person)
		targets = [item for item in progress if item.get("prosecution_status") == "고발대상자"]
		if not targets:
			continue
		latest = targets[-1]
		result.append({
			"military_number": person.military_number,
			"name": person.name,
			"branch": person.branch,
			"rank": person.rank,
			"service_year": person.service_year,
			"squad_id": person.squad_id,
			"mobilization_status": person.mobilization_status,
			"prosecution_reason": latest.get("prosecution_reason"),
			"consecutive_unexcused_absences": max(
				int(item.get("consecutive_unexcused_absences", 0)) for item in targets
			),
			"target_years": [int(item["service_year"]) for item in targets],
		})
	return result


@router.get("/training-review-targets", dependencies=[Depends(require_viewer)])
def list_training_review_targets(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	"""List incomplete training obligations for review, not as legal prosecution findings."""
	people = db.scalars(select(Person).order_by(Person.military_number)).all()
	today = date.today()
	result: list[dict[str, object]] = []
	backfilled = False
	for person in people:
		if person.service_year is None or person.service_year < 1:
			continue
		derived = db.scalar(select(TrainingYearResult.id).where(
			TrainingYearResult.person_id == person.military_number
		).limit(1))
		if derived is None:
			recalculate_person(db, person.military_number, 1, "initial_backfill", "system")
			backfilled = True
		carryovers = db.scalars(select(TrainingCarryover).where(
			TrainingCarryover.person_id == person.military_number,
			TrainingCarryover.remaining_hours > 0,
		)).all()
		year_results = db.scalars(select(TrainingYearResult).where(
			TrainingYearResult.person_id == person.military_number
		)).all()
		records = db.scalars(select(Education).where(
			Education.person_id == person.military_number,
			Education.attendance_status.in_(ROUND_SCHEDULED),
			Education.scheduled_date.is_not(None),
		)).all()
		last_session_days = training_last_session_days(db, records)
		absence_records = db.scalars(select(Education).where(
			Education.person_id == person.military_number,
			Education.attendance_status.in_(UNEXCUSED_ABSENCE),
		)).all()
		excused_absence_ids = _approved_excusal_record_ids(
			db, person.military_number, absence_records
		)
		unconfirmed_absences = [
			record for record in absence_records
			if not record.confirmed_by and record.id not in excused_absence_ids
		]
		overdue = [record for record in records if last_session_days.get(record.id)
		           and today > last_session_days[record.id] + timedelta(days=OVERDUE_GRACE_DAYS)]
		future_scheduled_years = {
			record.education_year for record in records
			if last_session_days.get(record.id) and last_session_days[record.id] >= today
		}
		review_years = {row.origin_year for row in carryovers}
		review_years.update(row.service_year for row in year_results if row.needs_review_reason)
		review_years.update(record.education_year for record in overdue)
		review_years.update(record.education_year for record in unconfirmed_absences)
		review_years.update(
			row.service_year for row in year_results
			if row.service_year == person.service_year and row.unmet_hours > 0
			and row.service_year not in future_scheduled_years
		)
		if not review_years:
			continue
		current_unmet = sum(
			row.unmet_hours for row in year_results
			if row.service_year == person.service_year and not row.needs_review_reason
		)
		remaining_hours = sum(row.remaining_hours for row in carryovers) + current_unmet
		review_rows = [
			{
				"origin_year": row.origin_year,
				"training_type": row.training_type,
				"round": row.current_round,
				"remaining_hours": row.remaining_hours,
				"status": row.status,
				"reason": row.reason_code,
			}
			for row in carryovers
		]
		review_rows.extend(
			{
				"origin_year": row.service_year,
				"training_type": "NEEDS_REVIEW",
				"round": None,
				"remaining_hours": None,
				"status": "needs_review",
				"reason": row.needs_review_reason,
			}
			for row in year_results if row.needs_review_reason
		)
		review_rows.extend(
			{
				"origin_year": record.education_year,
				"training_type": record.training_type,
				"round": record.training_round,
				"remaining_hours": None,
				"status": "unconfirmed",
				"reason": "overdue_result_not_entered",
			}
			for record in overdue
		)
		review_rows.extend(
			{
				"origin_year": record.education_year,
				"training_type": record.training_type,
				"round": record.training_round,
				"remaining_hours": None,
				"status": "recorded_absence_metadata_missing",
				"reason": "confirming_user_metadata_missing",
			}
			for record in unconfirmed_absences
		)
		result.append({
				"military_number": person.military_number,
				"name": person.name,
				"branch": person.branch,
				"rank": person.rank,
				"service_year": person.service_year,
				"squad_id": person.squad_id,
				"review_years": sorted(review_years),
				"remaining_hours": remaining_hours,
				"review_rows": review_rows,
			})
	if backfilled:
		db.commit()
	return result

@persons_router.get("/assignment-candidates", dependencies=[Depends(require_viewer)])
def list_assignment_candidates(
	position: str = Query(..., description="Wartime position, for example 행정병"),
	branch: str | None = Query(default=None),
	db: Session = Depends(get_db),
) -> dict[str, dict[str, list[dict[str, object]]]]:
	
	people = db.scalars(select(Person).order_by(Person.military_number)).all()
	groups = grouped_candidates(people, position, branch)
	return {
		branch_name: {
			personnel_category: [
				{
					"military_number": candidate.person.military_number,
					"name": candidate.person.name,
					"rank": candidate.person.rank,
					"service_year": candidate.person.service_year,
					"specialty": candidate.person.specialty,
					"position": candidate.person.position,
					"tier": candidate.tier,
				}
				for candidate in candidates
			]
			for personnel_category, candidates in personnel_groups.items()
		}
		for branch_name, personnel_groups in groups.items()
	}

@router.get("", response_model=list[PersonRead], dependencies=[Depends(require_viewer)])
@persons_router.get("", response_model=list[PersonRead], dependencies=[Depends(require_viewer)])
def list_reservists(
	query_text: str | None = Query(default=None, alias="query"),
	branch: str | None = Query(default=None),
	rank: str | None = Query(default=None),
	status: str | None = Query(default=None),
	mobilization_status: str | None = Query(default=None),
	platoon: str | None = Query(default=None, description="소대 이름, 예: 1소대"),
	category: Literal["병사", "부사관", "장교", "간부"] | None = Query(default=None),
	assigned: bool | None = Query(default=None, description="true=편성, false=미편성"),
	db: Session = Depends(get_db),
) -> list[Person]:
	return search_people(db, PersonSearch(
		query_text=query_text,
		branch=branch,
		rank=rank,
		status=status,
		mobilization_status=mobilization_status,
		platoon=platoon,
		category=category,
		assigned=assigned,
	))


def _current_roster_hours(
	db: Session, people: list[Person]
) -> dict[str, dict[str, object]]:
	people_with_year = [person for person in people if person.service_year is not None]
	if not people_with_year:
		return {}
	person_ids = [person.military_number for person in people_with_year]
	results = db.scalars(
		select(TrainingYearResult).where(TrainingYearResult.person_id.in_(person_ids))
	).all()
	results_by_year: dict[tuple[str, int], list[TrainingYearResult]] = {}
	for row in results:
		results_by_year.setdefault((row.person_id, row.service_year), []).append(row)

	carryovers = db.scalars(
		select(TrainingCarryover).where(
			TrainingCarryover.person_id.in_(person_ids),
			or_(
				TrainingCarryover.reason_code.is_(None),
				TrainingCarryover.reason_code != "no_longer_required",
			),
		)
	).all()
	carryovers_by_person: dict[str, list[TrainingCarryover]] = {}
	for row in carryovers:
		carryovers_by_person.setdefault(row.person_id, []).append(row)
	allocations: dict[int, list[tuple[int, int]]] = {}
	if carryovers:
		allocation_rows = db.execute(
			select(
				TrainingCarryoverResolution.carryover_id,
				Education.education_year,
				TrainingCarryoverResolution.hours,
			)
			.join(Education, Education.id == TrainingCarryoverResolution.education_id)
			.where(TrainingCarryoverResolution.carryover_id.in_([row.id for row in carryovers]))
		).all()
		for carryover_id, education_year, hours in allocation_rows:
			allocations.setdefault(carryover_id, []).append((education_year, hours))

	summaries: dict[str, dict[str, object]] = {}
	for person in people_with_year:
		service_year = int(person.service_year)
		year_results = results_by_year.get((person.military_number, service_year), [])
		if not year_results:
			current = next(
				(item for item in all_training_progress(db, person) if item["service_year"] == service_year),
				None,
			)
			if current is None:
				continue
			counted = int(current["completed_hours"])
			credited = int(current.get("credited_hours", 0))
			required = int(current.get("target_hours", current["required_hours"]))
			carryover_hours = int(current.get("carryover_hours", 0))
			unmet = int(current.get("unmet_required_hours", current["remaining_hours"]))
			remaining = int(current["remaining_hours"])
			review_reason = current.get("needs_review_reason")
			training_status = str(current["training_status"])
		else:
			review = next((row for row in year_results if row.needs_review_reason), None)
			if review is not None:
				counted = credited = required = carryover_hours = unmet = remaining = 0
				review_reason = review.needs_review_reason
				training_status = "NEEDS_REVIEW"
			else:
				required = sum(row.required_hours for row in year_results)
				counted = sum(row.counted_hours for row in year_results)
				credited = sum(row.credited_hours for row in year_results)
				carryover_hours = sum(
					max(
						0,
						row.original_hours - sum(
							hours for allocated_year, hours in allocations.get(row.id, [])
							if allocated_year <= service_year
						),
					)
					for row in carryovers_by_person.get(person.military_number, [])
					if row.origin_year < service_year
				)
				unmet = max(required - counted - credited, 0)
				remaining = unmet + carryover_hours
				review_reason = None
				training_status = (
					"훈련 미이수" if required > 0 and remaining > 0
					else "훈련 이수" if required > 0
					else "훈련 대상 아님"
				)
		summaries[person.military_number] = {
			"required_hours": required,
			"counted_hours": counted,
			"credited_hours": credited,
			"recognized_hours": counted + credited,
			"carryover_hours": carryover_hours,
			"unmet_required_hours": unmet,
			"remaining_hours": remaining,
			"training_status": training_status,
			"needs_review_reason": review_reason,
			"over_limit": counted + credited > required,
			"is_incomplete": remaining > 0,
		}
	return summaries


@persons_router.get("/roster", response_model=list[PersonRosterRead], dependencies=[Depends(require_viewer)])
def list_persons_with_training_summary(
	query_text: str | None = Query(default=None, alias="query"),
	branch: str | None = Query(default=None),
	rank: str | None = Query(default=None),
	status: str | None = Query(default=None),
	mobilization_status: str | None = Query(default=None),
	platoon: str | None = Query(default=None, description="소대 이름, 예: 1소대"),
	category: Literal["병사", "부사관", "장교", "간부"] | None = Query(default=None),
	assigned: bool | None = Query(default=None, description="true=편성, false=미편성"),
	db: Session = Depends(get_db),
) -> list[PersonRosterRead]:
	people = search_people(db, PersonSearch(
		query_text=query_text,
		branch=branch,
		rank=rank,
		status=status,
		mobilization_status=mobilization_status,
		platoon=platoon,
		category=category,
		assigned=assigned,
	))
	hours_by_person = _current_roster_hours(db, people)
	latest_records: dict[tuple[str, int], Education] = {}
	person_ids = [person.military_number for person in people]
	if person_ids:
		for record in db.scalars(
			select(Education)
			.where(Education.person_id.in_(person_ids))
			.order_by(Education.id)
		).all():
			latest_records[(record.person_id, record.education_year)] = record

	result: list[PersonRosterRead] = []
	for person in people:
		summary = hours_by_person.get(person.military_number)
		if summary is not None:
			record = latest_records.get((person.military_number, person.service_year or 0))
			attendance = record.attendance_status if record is not None else None
			training_status = str(summary["training_status"])
			if training_status != "NEEDS_REVIEW" and attendance == "조기퇴소":
				training_status = f"조기퇴소 · {record.training_round}차"
			elif training_status != "NEEDS_REVIEW" and attendance in {"보류", "round_hold"}:
				training_status = "보류"
			elif training_status != "NEEDS_REVIEW" and attendance in {"연기", "postponed"}:
				training_status = "연기"
			summary = {
				**summary,
				"training_status": training_status,
				"latest_round": record.training_round if record is not None else None,
				"latest_status": attendance,
				"latest_schedule_id": record.schedule_id if record is not None else None,
			}
		elif person.service_year is None:
			summary = {
				"required_hours": 0,
				"counted_hours": 0,
				"credited_hours": 0,
				"recognized_hours": 0,
				"carryover_hours": 0,
				"unmet_required_hours": 0,
				"remaining_hours": 0,
				"training_status": "NEEDS_REVIEW",
				"needs_review_reason": "복무연차 미등록",
				"latest_round": None,
				"latest_status": None,
				"latest_schedule_id": None,
				"over_limit": False,
				"is_incomplete": False,
			}
		result.append(PersonRosterRead.model_validate({
			**{
				column.name: getattr(person, column.name)
				for column in Person.__table__.columns
			},
			"training_hours_summary": summary,
		}))
	return result

@persons_router.get("/profile-options")
def get_profile_options():
	return profile_options()


@persons_router.patch("/{military_number}/profile", response_model=PersonRead,
	dependencies=[Depends(require_scheduler)])
def update_profile(
	military_number: str,
	payload: PersonProfileUpdate,
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
):
	person = _profile_person(db, military_number)
	try:
		return save_profile(
			db, person, payload.model_dump(exclude_unset=True),
			actor.username, actor.id,
		)
	except ProfileError as error:
		raise HTTPException(status_code=422, detail={"fields": error.fields}) from error
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=409, detail="군번 중복 또는 연결 정보 충돌로 저장하지 못했습니다.") from error


@persons_router.patch("/{military_number}/annual-status/{service_year}",
	dependencies=[Depends(require_scheduler)])
def update_annual_status(
	military_number: str,
	service_year: int,
	payload: dict[str, object],
	db: Session = Depends(get_db),
	actor: User | None = Depends(require_scheduler),
) -> dict[str, object]:
	allowed = {"mobilization_status", "semester_completed"}
	if not payload or set(payload) - allowed:
		raise HTTPException(status_code=422, detail="Invalid annual-status fields")
	if "mobilization_status" in payload and not isinstance(payload["mobilization_status"], str):
		raise HTTPException(status_code=422, detail="mobilization_status must be a string")
	if "semester_completed" in payload and payload["semester_completed"] is not None and not isinstance(payload["semester_completed"], bool):
		raise HTTPException(status_code=422, detail="semester_completed must be a boolean or null")
	person = _profile_person(db, military_number)
	row = db.get(AnnualStatus, (military_number, service_year))
	if row is None:
		status_value = payload.get("mobilization_status", person.mobilization_status)
		if not isinstance(status_value, str) or not status_value:
			raise HTTPException(status_code=422, detail="Annual mobilization status is required")
		row = AnnualStatus(
			person_id=military_number,
			service_year=service_year,
			mobilization_status=status_value,
			semester_completed=payload.get("semester_completed"),
		)
		db.add(row)
		db.flush()
	before = {
		"mobilization_status": row.mobilization_status,
		"semester_completed": row.semester_completed,
	}
	for key, value in payload.items():
		setattr(row, key, value)
	after = {
		"mobilization_status": row.mobilization_status,
		"semester_completed": row.semester_completed,
	}
	db.add(AuditLog(
		user_id=actor.id if isinstance(actor, User) else None,
		action="annual_status.update",
		table_name="annual_status",
		actor_label=actor.username if isinstance(actor, User) else "direct-call",
		before_data=json.dumps(before, ensure_ascii=False, sort_keys=True),
		after_data=json.dumps(after, ensure_ascii=False, sort_keys=True),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	recalculate_person(
		db, military_number, service_year, "status_change",
		actor.username if isinstance(actor, User) else "direct-call",
		actor_user_id=actor.id if isinstance(actor, User) else None,
	)
	db.commit()
	return {"person_id": military_number, "service_year": service_year, **after}


def _profile_person(db: Session, military_number: str):
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="대상자를 찾을 수 없습니다. 목록을 새로고침하세요.")
	return person


@router.get("/{military_number}", response_model=PersonRead, dependencies=[Depends(require_viewer)])
@persons_router.get("/{military_number}", response_model=PersonRead, dependencies=[Depends(require_viewer)])
def get_reservist(military_number: str, db: Session = Depends(get_db)) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	return person

@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED,
	dependencies=[Depends(require_scheduler)])
@persons_router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED,
	dependencies=[Depends(require_scheduler)])
def create_reservist(
	payload: PersonCreate,
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
) -> Person:
	try:
		return create_person(db, payload, actor_user_id=actor.id)
	except IntegrityError as error:
		db.rollback()
		raise HTTPException(status_code=409, detail="Military number already exists") from error

@router.patch("/{military_number}", response_model=PersonRead,
	dependencies=[Depends(require_scheduler)])
@persons_router.patch("/{military_number}", response_model=PersonRead,
	dependencies=[Depends(require_scheduler)])
def update_reservist(
	military_number: str,
	payload: PersonUpdate,
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")

	updates = payload.model_dump(exclude_unset=True)
	new_mobilization_status = updates.pop("mobilization_status", None)
	for field, value in updates.items():
		setattr(person, field, value)
	if updates.get("squad_id") is not None and not is_assignable(person):
		db.rollback()
		raise HTTPException(status_code=409, detail=f"편성 대상이 아닙니다 ({not_assignable_reason(person)})")
	if new_mobilization_status is not None and new_mobilization_status != person.mobilization_status:
		apply_mobilization_status_change(db, person, new_mobilization_status)
	from user.app.services.training_recalculation import recalculate_person
	recalculate_person(
		db, military_number, 1, "status_change", actor.username,
		actor_user_id=actor.id,
	)
	db.commit()
	db.refresh(person)
	return person

@router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(require_scheduler)])
@persons_router.delete("/{military_number}", status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(require_scheduler)])
def delete_reservist(
	military_number: str,
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
) -> None:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	db.add(AuditLog(
		user_id=actor.id,
		action="reservist.delete",
		table_name="person",
		entity_key=person.military_number,
		actor_label=actor.username,
		before_data=json.dumps({
			"military_number": person.military_number,
			"name": person.name,
			"status": person.status,
		}, ensure_ascii=False, sort_keys=True),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	for model in (AnnualStatus, Assignment, Education):
		db.query(model).filter(model.person_id == military_number).delete(
			synchronize_session=False
		)
	db.delete(person)
	db.commit()
