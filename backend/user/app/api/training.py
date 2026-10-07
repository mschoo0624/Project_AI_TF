"""Reserve-training hour APIs."""
"""
훈련시간과 연간 훈련 진행률을 관리합니다.

라우터 기본 경로는 /reservists이지만 실제 기능은 훈련시간 주소에 붙습니다.

GET 기능
다음 정보를 반환합니다.

현재 복무연도
연도별 훈련 진행률
연도별 동원 상태
목표 훈련시간
이월시간
남은 시간
고발 위험
실제 교육 기록
POST 기능
훈련 기록을 등록합니다.

검증하는 항목:

미래 복무연도인지 여부
훈련시간이 양수인지 여부
불참 기록인데 시간이 입력됐는지 여부
목표시간보다 많은 시간이 등록됐는지 여부
출석 상태가 유효한지 여부
"""
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.audit_log import AuditLog
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.user import User
from user.app.models.training_recalculation import (
	TrainingCarryover,
	TrainingCarryoverResolution,
	TrainingStatusPolicy,
	TrainingYearResult,
)
from user.app.schemas.education import (
	TrainingRecordCreate,
	TrainingRecordRead,
	TrainingRecordUpdate,
)
from user.app.services.training import (
	all_training_progress,
    ATTENDANCE_HOURS_REQUIRED,
    ATTENDANCE_ZERO_HOURS,
	ROUND_HOLD,
	ROUND_POSTPONED,
	ROUND_SCHEDULED,
	UNEXCUSED_ABSENCE,
    mobilization_status_for_year,
    training_record_required_hours,
	training_round_sequence_error,
)
from user.app.services.training_recalculation import (
	postponement_limit_warnings,
	recalculate_all_people,
	recalculate_person,
)
from user.app.services.auth import require_approver, require_scheduler, require_viewer

router = APIRouter(prefix="/reservists", tags=["training"])
persons_training_router = APIRouter(prefix="/persons", tags=["training"])


def _get_person_or_404(military_number: str, db: Session) -> Person:
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	return person


def _approved_deferral_record_ids(
	db: Session, person_id: str, records: list[Education]
) -> set[int]:
	rows = db.scalars(select(Postponement).where(
		Postponement.person_id == person_id,
		Postponement.status == "approved",
		Postponement.type.in_({"delay", "연기"}),
	)).all()
	approved: set[int] = set()
	for record in records:
		for item in rows:
			linked = item.education_record_id == record.id
			in_period = (
				record.scheduled_date is not None
				and item.start_date is not None
				and item.end_date is not None
				and item.start_date <= record.scheduled_date <= item.end_date
				and (item.training_year is None or item.training_year == record.training_year)
			)
			if linked or in_period:
				approved.add(record.id)
				break
	return approved


def _validate_session_date(
	attendance_status: str,
	scheduled_date: date | None,
	*,
	require_date: bool,
) -> None:
	today = date.today()
	if attendance_status in ROUND_SCHEDULED:
		if scheduled_date is None or scheduled_date <= today:
			raise HTTPException(status_code=422, detail="Scheduled training date must be in the future")
		return
	if scheduled_date is None:
		if require_date and attendance_status in (
			ATTENDANCE_HOURS_REQUIRED | UNEXCUSED_ABSENCE | ROUND_POSTPONED | ROUND_HOLD
		):
			raise HTTPException(status_code=422, detail="Training result requires its scheduled date")
		return
	if attendance_status in ATTENDANCE_HOURS_REQUIRED | UNEXCUSED_ABSENCE and scheduled_date >= today:
		raise HTTPException(status_code=422, detail="Attendance or absence can only be recorded after the training date")


def _record_snapshot(record: Education) -> dict[str, object]:
	return {
		"education_year": record.education_year,
		"training_year": record.training_year,
		"scheduled_date": record.scheduled_date.isoformat() if record.scheduled_date else None,
		"training_type": record.training_type,
		"training_round": record.training_round,
		"attendance_status": record.attendance_status,
		"training_hours": record.training_hours,
		"confirmed_by": record.confirmed_by,
		"confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
		"schedule_id": record.schedule_id,
		"source_kind": record.source_kind,
		"notes": record.notes,
		"version": record.version,
	}


def _recalculation_diff(before_text: str | None, after_text: str | None) -> list[dict[str, object]]:
	try:
		before = json.loads(before_text or "{}")
		after = json.loads(after_text or "{}")
	except json.JSONDecodeError:
		return []
	collections = (
		("results", ("service_year", "training_type")),
		("carryovers", ("origin_year", "training_type", "origin_round")),
		("rounds", ("training_type",)),
	)
	changes: list[dict[str, object]] = []
	for collection, identity_fields in collections:
		before_rows = {
			tuple(row.get(field) for field in identity_fields): row
			for row in before.get(collection, [])
		}
		after_rows = {
			tuple(row.get(field) for field in identity_fields): row
			for row in after.get(collection, [])
		}
		for identity in sorted(set(before_rows) | set(after_rows), key=str):
			old = before_rows.get(identity)
			new = after_rows.get(identity)
			if old != new:
				changes.append({
					"entity": collection,
					"key": " · ".join(str(value) for value in identity),
					"before": old,
					"after": new,
				})
	return changes


@persons_training_router.get("/{military_number}/training-progress")
def get_training_progress(
	military_number: str,
	db: Session = Depends(get_db),
) -> list[dict[str, object]]:
	person = _get_person_or_404(military_number, db)
	return all_training_progress(db, person)


@router.post("/training/recalculate/{military_number}", dependencies=[Depends(require_scheduler)])
def recalculate_one_person(
	military_number: str,
	from_year: int = 1,
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
) -> dict[str, object]:
	try:
		result = recalculate_person(
			db, military_number, from_year, "manual", actor.username,
			actor_user_id=actor.id,
		)
	except ValueError as error:
		raise HTTPException(status_code=404, detail=str(error)) from error
	db.commit()
	return result


@router.post("/training/recalculate-all", dependencies=[Depends(require_scheduler)])
def recalculate_everyone(
	db: Session = Depends(get_db),
	actor: User = Depends(require_scheduler),
) -> dict[str, object]:
	result = recalculate_all_people(
		db, "manual", actor.username, actor_user_id=actor.id
	)
	db.commit()
	return result


@router.get("/training/status-policies")
def list_training_status_policies(db: Session = Depends(get_db)) -> list[dict[str, object]]:
	return [
		{
			"status_key": row.status_key,
			"counts_hours": row.counts_hours,
			"credits_hours": row.credits_hours,
			"advances_round": row.advances_round,
			"confirmed_absence": row.confirmed_absence,
			"enabled": row.enabled,
			"prosecution_kind": row.prosecution_kind,
		}
		for row in db.scalars(select(TrainingStatusPolicy).order_by(TrainingStatusPolicy.status_key)).all()
	]


@router.patch("/training/status-policies/{status_key}", dependencies=[Depends(require_approver)])
def update_training_status_policy(
	status_key: str,
	payload: dict[str, object],
	db: Session = Depends(get_db),
	actor: User = Depends(require_approver),
) -> dict[str, object]:
	allowed = {
		"counts_hours", "credits_hours", "advances_round", "confirmed_absence",
		"enabled", "prosecution_kind",
	}
	if not payload or set(payload) - allowed:
		raise HTTPException(status_code=422, detail="Invalid status-policy fields")
	for key in allowed - {"prosecution_kind"}:
		if key in payload and not isinstance(payload[key], bool):
			raise HTTPException(status_code=422, detail=f"{key} must be a boolean")
	if "prosecution_kind" in payload and payload["prosecution_kind"] is not None and not isinstance(payload["prosecution_kind"], str):
		raise HTTPException(status_code=422, detail="prosecution_kind must be a string or null")
	row = db.get(TrainingStatusPolicy, status_key)
	if row is None:
		row = TrainingStatusPolicy(
			status_key=status_key,
			counts_hours=False,
			credits_hours=False,
			advances_round=False,
			confirmed_absence=False,
			enabled=True,
		)
		db.add(row)
		db.flush()
	before = {
		key: getattr(row, key)
		for key in allowed
	}
	for key, value in payload.items():
		setattr(row, key, value)
	after = {key: getattr(row, key) for key in allowed}
	db.add(AuditLog(
		action="training.status_policy.update",
		table_name="training_status_policy",
		user_id=actor.id,
		actor_label=actor.username,
		before_data=json.dumps(before, ensure_ascii=False, sort_keys=True),
		after_data=json.dumps(after, ensure_ascii=False, sort_keys=True),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	recalculate_all_people(
		db, "status_change", actor.username, actor_user_id=actor.id
	)
	db.commit()
	return {"status_key": status_key, **after}


@router.get("/{military_number}/training-hours", dependencies=[Depends(require_viewer)])
def get_training_hours(
	military_number: str,
	db: Session = Depends(get_db),
) -> dict[str, object]:
	person = _get_person_or_404(military_number, db)
	derived_exists = db.scalar(select(TrainingYearResult.id).where(
		TrainingYearResult.person_id == military_number
	).limit(1))
	if derived_exists is None:
		recalculate_person(db, military_number, 1, "initial_backfill", "system")
		db.commit()
	progress = all_training_progress(db, person)
	year_results = db.scalars(
		select(TrainingYearResult).where(TrainingYearResult.person_id == military_number)
		.order_by(TrainingYearResult.service_year, TrainingYearResult.training_type)
	).all()
	carryovers = db.scalars(
		select(TrainingCarryover).where(TrainingCarryover.person_id == military_number)
		.order_by(TrainingCarryover.origin_year, TrainingCarryover.training_type, TrainingCarryover.origin_round)
	).all()
	carryover_ids = [row.id for row in carryovers]
	resolutions = db.scalars(select(TrainingCarryoverResolution).where(
		TrainingCarryoverResolution.carryover_id.in_(carryover_ids)
	)).all() if carryover_ids else []
	resolutions_by_carryover: dict[int, list[dict[str, int]]] = {}
	for item in resolutions:
		resolutions_by_carryover.setdefault(item.carryover_id, []).append({
			"education_id": item.education_id,
			"hours": item.hours,
		})
	audits = db.scalars(
		select(AuditLog).where(
			AuditLog.table_name == "person_training",
			AuditLog.entity_key == military_number,
			AuditLog.action.like("training.recalculate.%"),
		).order_by(AuditLog.created_at.desc()).limit(10)
	).all()

	return {
		"military_number": military_number,
		"current_service_year": person.service_year,
		"progress": progress,
		"warnings": postponement_limit_warnings(db, military_number),
		"recalculation_audit": [
			{
				"id": row.id,
				"reason": row.action.removeprefix("training.recalculate."),
				"actor": row.actor_label,
				"created_at": row.created_at,
				"changes": _recalculation_diff(row.before_data, row.after_data),
			}
			for row in audits
		],
		"year_results": [
			{
				"service_year": row.service_year,
				"training_type": row.training_type,
				"required_hours": row.required_hours,
				"counted_hours": row.counted_hours,
				"credited_hours": row.credited_hours,
				"unmet_hours": row.unmet_hours,
				"carryover_status": row.carryover_status,
				"needs_review_reason": row.needs_review_reason,
			}
			for row in year_results
		],
		"carryovers": [
			{
				"id": row.id,
				"origin_year": row.origin_year,
				"training_type": row.training_type,
				"origin_round": row.origin_round,
				"current_round": row.current_round,
				"original_hours": row.original_hours,
				"remaining_hours": row.remaining_hours,
				"status": row.status,
				"reason_code": row.reason_code,
				"converted_from_type": row.converted_from_type,
				"resolutions": resolutions_by_carryover.get(row.id, []),
			}
			for row in carryovers
		],
		"records": [
			{
				"id": record.id,
				"education_year": record.education_year,
				"training_year": record.training_year,
				"scheduled_date": record.scheduled_date,
				"training_type": record.training_type,
				"training_round": record.training_round,
				"mobilization_status": next(
					(
						status.mobilization_status
						for status in person.annual_statuses
						if status.service_year == record.education_year
					),
					person.mobilization_status,
				),
				"attendance_status": record.attendance_status,
				"training_hours": record.training_hours,
				"source_kind": record.source_kind,
				"confirmed_by": record.confirmed_by,
				"version": record.version,
				"required_hours": training_record_required_hours(
					record.training_type, record.education_year,
					mobilization_status_for_year(db, person, record.education_year),
					person.branch, person.rank, person.position,
					bool(progress[record.education_year]["officer_type_ii_makeup"]),
				),
				"notes": record.notes,
			}
			for record in db.scalars(
				select(Education)
				.where(Education.person_id == military_number)
				.order_by(Education.education_year, Education.training_year, Education.id)
			).all()
		],
	}

@router.post(
	"/{military_number}/training-hours",
	response_model=TrainingRecordRead,
	status_code=status.HTTP_201_CREATED,
)
def add_training_record(
	military_number: str,
	payload: TrainingRecordCreate,
	db: Session = Depends(get_db),
	current_user: User | None = Depends(require_scheduler),
) -> Education:
	actor_label = current_user.username if isinstance(current_user, User) else "direct-call"
	actor_user_id = current_user.id if isinstance(current_user, User) else None
	actor_role = current_user.role if isinstance(current_user, User) else "approver"
	confirmer = actor_label
	person = db.get(Person, military_number)
	if person is None:
		raise HTTPException(status_code=404, detail="Reservist not found")
	if person.service_year is not None and payload.service_year > person.service_year:
		raise HTTPException(
		status_code=400,
		detail="Cannot record training for a future service year",
	)

	progress = all_training_progress(db, person)
	# Progress includes year 0, so the service year is its list index.
	year_progress = progress[payload.service_year]
	required = int(year_progress["required_hours"])
	if required == 0:
		raise HTTPException(
		status_code=400,
		detail="This service year has no scheduled or carried-over training requirement",
	)
	completed = int(year_progress["completed_hours"])
	if payload.attendance_status not in ATTENDANCE_HOURS_REQUIRED and payload.attendance_status not in ATTENDANCE_ZERO_HOURS:
		raise HTTPException(status_code=422, detail="Invalid attendance status")
	if payload.attendance_status in UNEXCUSED_ABSENCE and not confirmer:
		raise HTTPException(status_code=422, detail="A named confirmer is required for an unexcused absence")
	if (
		payload.attendance_status in UNEXCUSED_ABSENCE
		and (payload.training_round >= 3 or payload.training_type in {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"})
		and actor_role != "approver"
	):
		raise HTTPException(status_code=403, detail="An approver must confirm this absence")
	_validate_session_date(payload.attendance_status, payload.scheduled_date, require_date=True)
	training_year = payload.training_year or (
		payload.scheduled_date.year if payload.scheduled_date else None
	) or person.service_year or payload.service_year
	if payload.scheduled_date and training_year != payload.scheduled_date.year:
		raise HTTPException(status_code=422, detail="Training year must match the scheduled date's calendar year")
	if payload.attendance_status in ATTENDANCE_HOURS_REQUIRED and payload.training_hours == 0:
		raise HTTPException(status_code=422, detail="Completed training must include positive hours")
	if payload.attendance_status not in ATTENDANCE_HOURS_REQUIRED and payload.training_hours != 0:
		raise HTTPException(status_code=422, detail="Non-completed training must have zero hours")
	remaining = max(required - completed, 0)
	if payload.attendance_status in ATTENDANCE_HOURS_REQUIRED and payload.training_hours > remaining:
		raise HTTPException(
		status_code=400,
		detail=f"Training hours exceed the remaining allowance ({remaining} hours)",
	)
	year_records = db.scalars(
		select(Education).where(
			Education.person_id == military_number,
			Education.education_year == payload.service_year,
		)
	).all()
	record_required = training_record_required_hours(
		payload.training_type,
		payload.service_year,
		mobilization_status_for_year(db, person, payload.service_year),
		person.branch,
		person.rank,
		person.position,
		bool(year_progress["officer_type_ii_makeup"]),
	)
	sequence_error = training_round_sequence_error(
		year_records,
		payload.training_type,
		payload.training_round,
		payload.attendance_status,
		payload.training_hours,
		record_required,
		approved_deferral_record_ids=_approved_deferral_record_ids(db, military_number, year_records),
		attempt_confirmed=bool(confirmer),
	)
	if sequence_error:
		raise HTTPException(status_code=422, detail=sequence_error)

	record = Education(
		person_id=military_number,
		education_year=payload.service_year,
		training_year=training_year,
		scheduled_date=payload.scheduled_date,
		training_type=payload.training_type,
		training_round=payload.training_round,
		attendance_status=payload.attendance_status,
		training_hours=payload.training_hours,
		source_kind="manual",
		confirmed_by=confirmer if confirmer and payload.attendance_status in UNEXCUSED_ABSENCE else None,
		confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None)
		if payload.attendance_status in UNEXCUSED_ABSENCE else None,
		notes=payload.notes,
	)
	db.add(record)
	db.flush()
	db.add(AuditLog(
		action="training_record.create",
		table_name="education",
		record_id=record.id,
		user_id=actor_user_id,
		actor_label=actor_label or "미인증 요청",
		after_data=json.dumps(_record_snapshot(record), ensure_ascii=False),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	recalculate_person(
		db, military_number, payload.service_year, "attendance_record_added", actor_label,
		actor_user_id=actor_user_id,
	)
	db.commit()
	db.refresh(record)
	return record


@router.patch(
	"/{military_number}/training-hours/{record_id}",
	response_model=TrainingRecordRead,
)
def update_training_record(
	military_number: str,
	record_id: int,
	payload: TrainingRecordUpdate,
	db: Session = Depends(get_db),
	current_user: User | None = Depends(require_scheduler),
	actor: str | None = None,
) -> Education:
	actor_label = current_user.username if isinstance(current_user, User) else (actor or "direct-call")
	actor_user_id = current_user.id if isinstance(current_user, User) else None
	actor_role = current_user.role if isinstance(current_user, User) else "approver"
	person = _get_person_or_404(military_number, db)
	record = db.get(Education, record_id)
	if record is None or record.person_id != military_number:
		raise HTTPException(status_code=404, detail="Training record not found")

	progress = all_training_progress(db, person)
	db.refresh(record)
	if payload.expected_version is None:
		raise HTTPException(status_code=428, detail="Expected record version is required")
	if payload.expected_version != record.version:
		raise HTTPException(status_code=409, detail="Training record changed; reload before saving")

	new_service_year = payload.service_year if payload.service_year is not None else record.education_year
	new_training_year = payload.training_year if payload.training_year is not None else record.training_year
	new_training_type = payload.training_type if payload.training_type is not None else record.training_type
	new_training_round = payload.training_round if payload.training_round is not None else record.training_round
	new_attendance_status = payload.attendance_status if payload.attendance_status is not None else record.attendance_status
	new_training_hours = payload.training_hours if payload.training_hours is not None else record.training_hours
	new_scheduled_date = payload.scheduled_date if payload.scheduled_date is not None else record.scheduled_date
	new_confirmer = actor_label
	old_service_year = record.education_year

	if person.service_year is not None and new_service_year > person.service_year:
		raise HTTPException(
			status_code=400,
			detail="Cannot record training for a future service year",
		)

	if new_attendance_status not in ATTENDANCE_HOURS_REQUIRED and new_attendance_status not in ATTENDANCE_ZERO_HOURS:
		raise HTTPException(status_code=422, detail="Invalid attendance status")
	if new_attendance_status in UNEXCUSED_ABSENCE and not record.confirmed_by and not new_confirmer:
		raise HTTPException(status_code=422, detail="A named confirmer is required for an unexcused absence")
	requires_approver = (
		(new_attendance_status in UNEXCUSED_ABSENCE and (
			new_training_round >= 3
			or new_training_type in {"동원훈련Ⅰ형", "동원훈련I형", "동원훈련1형"}
		))
		or (record.attendance_status in UNEXCUSED_ABSENCE and new_attendance_status not in UNEXCUSED_ABSENCE)
	)
	is_absence_reversal = (
		record.attendance_status in UNEXCUSED_ABSENCE
		and new_attendance_status not in UNEXCUSED_ABSENCE
	)
	if is_absence_reversal and not (payload.reversal_reason and payload.reversal_reason.strip()):
		raise HTTPException(status_code=422, detail="A reason is required to reverse an unexcused absence")
	if requires_approver and actor_role != "approver":
		raise HTTPException(status_code=403, detail="An approver must confirm or reverse this absence")
	status_changed = new_attendance_status != record.attendance_status
	date_changed = new_scheduled_date != record.scheduled_date
	_validate_session_date(
		new_attendance_status,
		new_scheduled_date,
		require_date=status_changed or date_changed,
	)
	new_training_year = new_training_year or (new_scheduled_date.year if new_scheduled_date else None)
	if new_scheduled_date and new_training_year and new_training_year != new_scheduled_date.year:
		raise HTTPException(status_code=422, detail="Training year must match the scheduled date's calendar year")
	if new_attendance_status in ATTENDANCE_HOURS_REQUIRED and new_training_hours == 0:
		raise HTTPException(status_code=422, detail="Completed training must include positive hours")
	if new_attendance_status not in ATTENDANCE_HOURS_REQUIRED and new_training_hours != 0:
		raise HTTPException(status_code=422, detail="Non-completed training must have zero hours")

	other_completed = int(
		db.scalar(
			select(func.coalesce(func.sum(Education.training_hours), 0)).where(
				Education.person_id == military_number,
				Education.education_year == new_service_year,
				Education.id != record_id,
				Education.attendance_status.in_(ATTENDANCE_HOURS_REQUIRED),
			)
		)
		or 0
	)

	year_progress = progress[new_service_year]
	required = int(year_progress["required_hours"])
	if required == 0:
		raise HTTPException(
			status_code=400,
			detail="This service year has no scheduled or carried-over training requirement",
		)

	remaining = max(required - other_completed, 0)
	if new_attendance_status in ATTENDANCE_HOURS_REQUIRED and new_training_hours > remaining:
		raise HTTPException(
			status_code=400,
			detail=f"Training hours exceed the remaining allowance ({remaining} hours)",
		)

	new_year_records = db.scalars(
		select(Education).where(
			Education.person_id == military_number,
			Education.education_year == new_service_year,
		)
	).all()
	new_required_hours = training_record_required_hours(
		new_training_type,
		new_service_year,
		mobilization_status_for_year(db, person, new_service_year),
		person.branch,
		person.rank,
		person.position,
		bool(progress[new_service_year]["officer_type_ii_makeup"]),
	)
	sequence_error = training_round_sequence_error(
		new_year_records,
		new_training_type,
		new_training_round,
		new_attendance_status,
		new_training_hours,
		new_required_hours,
		exclude_record_id=record_id,
		approved_deferral_record_ids=_approved_deferral_record_ids(db, military_number, new_year_records),
		attempt_confirmed=bool(new_confirmer),
	)
	if sequence_error:
		raise HTTPException(status_code=422, detail=sequence_error)

	group_changed = (
		new_service_year != record.education_year
		or new_training_type != record.training_type
		or new_training_round != record.training_round
	)
	if group_changed:
		old_year_records = new_year_records if new_service_year == record.education_year else db.scalars(
			select(Education).where(
				Education.person_id == military_number,
				Education.education_year == record.education_year,
			)
		).all()
		old_required_hours = training_record_required_hours(
			record.training_type,
			record.education_year,
			mobilization_status_for_year(db, person, record.education_year),
			person.branch,
			person.rank,
			person.position,
			bool(progress[record.education_year]["officer_type_ii_makeup"]),
		)
		old_sequence_error = training_round_sequence_error(
			old_year_records,
			record.training_type,
			None,
			None,
			0,
			old_required_hours,
			exclude_record_id=record_id,
			approved_deferral_record_ids=_approved_deferral_record_ids(db, military_number, old_year_records),
		)
		if old_sequence_error:
			raise HTTPException(status_code=422, detail=old_sequence_error)

	before_data = _record_snapshot(record)
	updates = payload.model_dump(exclude_unset=True, exclude={"expected_version", "reversal_reason"})
	updates.pop("expected_version", None)
	if "service_year" in updates:
		updates["education_year"] = updates.pop("service_year")
	if new_training_year is not None and "training_year" not in updates:
		updates["training_year"] = new_training_year
	if new_attendance_status in UNEXCUSED_ABSENCE:
		updates["confirmed_by"] = new_confirmer or record.confirmed_by
		updates["confirmed_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
	elif new_attendance_status not in UNEXCUSED_ABSENCE:
		updates["confirmed_by"] = None
		updates["confirmed_at"] = None
	updates["version"] = Education.version + 1
	result = db.execute(
		update(Education)
		.where(Education.id == record_id, Education.version == payload.expected_version)
		.values(**updates)
	)
	if result.rowcount != 1:
		db.rollback()
		raise HTTPException(status_code=409, detail="Training record changed; reload before saving")

	after_data = dict(before_data)
	for field, value in updates.items():
		if field == "version":
			after_data["version"] = payload.expected_version + 1
		else:
			key = "education_year" if field == "service_year" else field
			after_data[key] = value.isoformat() if hasattr(value, "isoformat") else value
	if is_absence_reversal:
		after_data["reversal_reason"] = payload.reversal_reason.strip()
	db.add(AuditLog(
		action="training_record.update",
		table_name="education",
		record_id=record_id,
		user_id=actor_user_id,
		actor_label=actor_label or "미인증 요청",
		before_data=json.dumps(before_data, ensure_ascii=False),
		after_data=json.dumps(after_data, ensure_ascii=False),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	recalculate_person(
		db,
		military_number,
		min(old_service_year, new_service_year),
		"attendance_record_edited",
		actor_label,
		actor_user_id=actor_user_id,
	)
	db.commit()
	db.refresh(record)
	return record


@router.delete("/{military_number}/training-hours/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_record(
	military_number: str,
	record_id: int,
	db: Session = Depends(get_db),
	current_user: User = Depends(require_scheduler),
) -> None:
	actor_label = current_user.username
	actor_user_id = current_user.id
	_get_person_or_404(military_number, db)
	record = db.get(Education, record_id)
	if record is None or record.person_id != military_number:
		raise HTTPException(status_code=404, detail="Training record not found")
	if (
		record.attendance_status in UNEXCUSED_ABSENCE
		and current_user.role != "approver"
	):
		raise HTTPException(status_code=403, detail="An approver must reverse this absence")
	deleted_year = record.education_year
	before_data = _record_snapshot(record)
	db.delete(record)
	db.flush()
	db.add(AuditLog(
		action="training_record.delete",
		table_name="education",
		record_id=record_id,
		user_id=actor_user_id,
		actor_label=actor_label or "미인증 요청",
		before_data=json.dumps(before_data, ensure_ascii=False),
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
	))
	recalculate_person(
		db, military_number, deleted_year, "attendance_record_deleted", actor_label,
		actor_user_id=actor_user_id,
	)
	db.commit()
