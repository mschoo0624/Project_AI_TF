"""Read-only Copilot tools: status summary, person summary,
data checks and change history. Nothing here writes to the DB."""

from __future__ import annotations

import json
from datetime import timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from user.app.copilot.common import ToolResult, squad_label
from user.app.copilot.schemas import UiAction
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.transfer_intake import TransferIntake
from user.app.services.assignment import is_assignable
from user.app.services.audit import recent_changes
from user.app.services.data_check import find_data_issues
from user.app.services.training import PARTIAL_HOLD
from user.app.services.training_summary import current_year_hours, prosecution_reasons

KST = timezone(timedelta(hours=9))
STATUS_NAMES = {"active": "복무 중", "on_leave": "휴가 중", "inactive": "비활성"}
POSTPONEMENT_TYPES = {"hold": "보류", "보류": "보류", "delay": "연기", "연기": "연기"}
POSTPONEMENT_STATUSES = {"pending": "결재 대기", "approved": "승인", "rejected": "반려"}
HELD_STATUSES = {"hold", "on_hold", "delay", "delayed", "postponed", "보류", "연기"}


def _filter(label: str, ids: list[str]) -> list[UiAction]:
	return [UiAction(type="navigate", tab="roster", subtab="people"),
		UiAction(type="filter", tab="roster", label=label, ids=ids)]


# ---------------------------------------------------------------- summarize_status

class StatusArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	focus: Literal["보류", "연기", "고발", "미편성", "교육", "결재"] | None = Field(
		default=None, description="특히 궁금한 항목. 예: '보류자 몇 명' → 보류")


def summarize_status(db: Session, args: StatusArgs) -> ToolResult:
	people = list(db.scalars(select(Person)).all())
	active = [person for person in people if person.status == "active"]
	hours = current_year_hours(db, people)
	targets = [number for number, item in hours.items() if item.required > 0]
	short = [number for number in targets if hours[number].remaining > 0]
	unassigned = [person for person in people if person.squad_id is None and is_assignable(person)]
	held = [person for person in people if person.status in HELD_STATUSES or person.mobilization_status in PARTIAL_HOLD]
	approved = db.execute(select(Postponement.type, func.count(func.distinct(Postponement.person_id)))
		.where(Postponement.status == "approved").group_by(Postponement.type)).all()
	approved_by_type = {POSTPONEMENT_TYPES.get(kind, kind): count for kind, count in approved}
	pending_postponements = db.scalar(select(func.count()).select_from(Postponement).where(Postponement.status == "pending")) or 0
	pending_transfers = db.scalar(select(func.count()).select_from(TransferIntake).where(TransferIntake.status == "pending")) or 0
	prosecution = prosecution_reasons(db, people, hours)
	issues = find_data_issues(db)

	lines = [
		f"전체 {len(people)}명 (복무 중 {len(active)}명)",
		f"편성 대상 미편성 {len(unassigned)}명",
		f"올해 교육 대상 {len(targets)}명 중 이수 완료 {len(targets) - len(short)}명, 미달 {len(short)}명",
		f"고발 검토 대상 {len(prosecution)}명",
		f"보류 상태 {len(held)}명 · 승인된 보류 {approved_by_type.get('보류', 0)}명 · 승인된 연기 {approved_by_type.get('연기', 0)}명",
		f"결재 대기: 보류·연기 신청 {pending_postponements}건, 전입 확인 {pending_transfers}건",
		f"이상 데이터 {len(issues)}종류" + (f" ({', '.join(issue.title for issue in issues)})" if issues else ""),
	]
	headline = {
		"보류": f"보류 상태인 인원은 {len(held)}명, 승인된 보류는 {approved_by_type.get('보류', 0)}명이에요.",
		"연기": f"승인된 연기는 {approved_by_type.get('연기', 0)}명이에요.",
		"고발": f"고발 검토 대상은 {len(prosecution)}명이에요. 명단은 \"고발 대상자 보여줘\"로 볼 수 있어요.",
		"미편성": f"편성 대상인데 미편성인 인원은 {len(unassigned)}명이에요.",
		"교육": f"올해 교육 시간을 못 채운 인원은 {len(short)}명이에요. 명단은 \"교육 미달자 보여줘\"로 볼 수 있어요.",
		"결재": f"결재 대기는 보류·연기 신청 {pending_postponements}건, 전입 확인 {pending_transfers}건이에요.",
	}.get(args.focus or "", "오늘 현황이에요.")
	actions: list[UiAction] = []
	if args.focus == "미편성":
		actions = _filter("편성 대상 미편성", [person.military_number for person in unassigned])
	elif args.focus == "보류" and held:
		actions = _filter("보류 상태", [person.military_number for person in held])
	return ToolResult(headline + "\n" + "\n".join(f"· {line}" for line in lines), actions)


# ------------------------------------------------------------------ person_summary

class PersonSummaryArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	military_number: str | None = Field(default=None, max_length=50, description="군번")
	name: str | None = Field(default=None, max_length=20, description="이름")


def _find_people(db: Session, args: PersonSummaryArgs) -> list[Person]:
	if args.military_number:
		person = db.get(Person, args.military_number.strip())
		return [person] if person else []
	name = (args.name or "").strip()
	exact = list(db.scalars(select(Person).where(Person.name == name)).all())
	if exact or len(name) < 3:
		return exact
	# "홍길동은", "홍길동의"처럼 조사가 붙은 경우
	return list(db.scalars(select(Person).where(Person.name == name[:-1])).all())


def person_summary(db: Session, args: PersonSummaryArgs) -> ToolResult:
	if not args.military_number and not args.name:
		return ToolResult("누구의 정보를 볼지 이름이나 군번을 알려 주세요. 예: \"홍길동 정보\"")
	people = _find_people(db, args)
	if not people:
		return ToolResult(f"'{args.military_number or args.name}'인 인원을 찾지 못했어요.")
	if len(people) > 1:
		listed = ", ".join(f"{person.name}({person.military_number}, {person.branch} {person.rank or ''})" for person in people[:5])
		return ToolResult(f"같은 이름이 {len(people)}명 있어요: {listed}. 군번으로 다시 물어봐 주세요.",
			_filter(f"'{args.name}' 동명이인", [person.military_number for person in people]))

	person = people[0]
	lines = [
		f"{person.name}({person.military_number}) · {person.branch} {person.rank or '계급 미등록'} · "
		f"{person.service_year if person.service_year is not None else '?'}년차 · {person.position or '직책 미지정'} · "
		f"{STATUS_NAMES.get(person.status, person.status)}",
		f"편성: {squad_label(db, person.squad_id) if person.squad_id else '미편성'}"
		+ ("" if is_assignable(person) or person.squad_id else " (편성 대상 아님)"),
		f"동원 상태: {person.mobilization_status or '미등록'}",
	]
	hours = current_year_hours(db, [person]).get(person.military_number)
	if hours is not None and hours.required > 0:
		carry = f", 이월 {hours.carryover}시간 포함" if hours.carryover else ""
		lines.append(f"올해 교육({hours.service_year}년차): 필요 {hours.required}시간{carry} 중 {hours.completed}시간 이수"
			+ (f", {hours.remaining}시간 남음" if hours.remaining else " (완료)"))
		reason = prosecution_reasons(db, [person], {person.military_number: hours}).get(person.military_number)
		if reason:
			lines.append(f"고발 검토 대상: {reason}")
	elif hours is not None:
		lines.append("올해 교육: 대상 아님")
	postponements = list(db.scalars(select(Postponement).where(Postponement.person_id == person.military_number)
		.order_by(Postponement.id.desc())).all())
	if postponements:
		lines.append(f"보류·연기 이력 {len(postponements)}건: " + "; ".join(
			f"{item.training_year or '?'}년차 {POSTPONEMENT_TYPES.get(item.type, item.type)} "
			f"{POSTPONEMENT_STATUSES.get(item.status, item.status)} ({item.reason[:20]})"
			for item in postponements[:3]))
	else:
		lines.append("보류·연기 이력 없음")
	return ToolResult("\n".join(lines), _filter(person.name, [person.military_number]))


# ---------------------------------------------------------------- check_data_issues

class DataCheckArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")


def check_data_issues(db: Session, args: DataCheckArgs) -> ToolResult:
	issues = find_data_issues(db)
	if not issues:
		return ToolResult("점검한 규칙에서 이상 데이터를 찾지 못했어요. (편성 대상, 분대 구성·정원, 연차, 동원 상태)")
	lines = [f"이상 데이터 {len(issues)}종류를 찾았어요."]
	for index, issue in enumerate(issues, 1):
		line = f"{index}. {issue.title} {len(issue.ids)}명"
		if issue.details:
			line += f" — {'; '.join(issue.details[:3])}"
		if issue.fix:
			line += f" → \"{issue.fix}\"라고 하면 해제안을 만들어 드려요."
		lines.append(line)
	lines.append("관련 인원 전체를 편성인원목록에 필터로 걸었어요.")
	ids = list(dict.fromkeys(number for issue in issues for number in issue.ids))
	return ToolResult("\n".join(lines), _filter("이상 데이터", ids))


# ------------------------------------------------------------------- recent_changes

class RecentChangesArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	limit: int = Field(default=5, ge=1, le=20, description="보여줄 기록 수")


def show_recent_changes(db: Session, args: RecentChangesArgs) -> ToolResult:
	rows = recent_changes(db, args.limit)
	if not rows:
		return ToolResult("아직 남은 변경 기록이 없어요. 편성·해제를 하면 여기에 기록돼요.")
	lines = [f"최근 변경 {len(rows)}건이에요."]
	ids: list[str] = []
	for row in rows:
		when = row.created_at.replace(tzinfo=timezone.utc).astimezone(KST).strftime("%m/%d %H:%M")
		lines.append(f"· {when} [{row.source or '?'}] {row.summary}")
		try:
			detail = json.loads(row.detail) if row.detail else None
		except json.JSONDecodeError:
			detail = None
		if isinstance(detail, list):
			ids.extend(str(item["military_number"]) for item in detail if isinstance(item, dict) and "military_number" in item)
	ids = list(dict.fromkeys(ids))
	return ToolResult("\n".join(lines), _filter("최근 변경 인원", ids) if ids else [])

