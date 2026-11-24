"""Read-only Copilot tool: 기간 안에 수정된 인원 ("오늘 수정한 인원 보여줘", "오늘 자동편성한 인원").

변경 기록(audit_log)과 결재 기록에서 사람을 가리키는 세 가지만 "수정"으로 센다.
  · 편성 변경: 편성·해제·재편성(자동 편성 포함) 기록의 detail에 든 인원
  · 훈련 기록 수정: 출석·결과 입력/수정/삭제/일괄 확정/상태 변경으로 다시 계산된 인원
  · 결재 승인: 기간 안에 보류·연기 신청이 승인된 인원
시스템이 자동으로 한 최초 재계산(initial_backfill), 조회·내보내기 기록은 사람이 고친 것이 아니므로 뺀다.
DB를 바꾸지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.common import ToolResult, josa
from user.app.copilot.insights import KST
from user.app.copilot.schemas import UiAction
from user.app.models.audit_log import AuditLog
from user.app.models.person import Person
from user.app.models.postpoment import Postponement

Period = Literal["오늘", "어제", "이번 주", "최근 7일", "이번 달"]
ChangeKind = Literal["편성", "훈련 기록", "결재"]
ASSIGNMENT, TRAINING, APPROVAL = "편성 변경", "훈련 기록 수정", "결재 승인"
KIND_NAMES = {"편성": ASSIGNMENT, "훈련 기록": TRAINING, "결재": APPROVAL}
# 목록 라벨: "오늘 수정된 인원", "오늘 편성된 인원". 이 라벨을 보고 "이 명단 엑셀로"가 같은 조건으로 내보낸다.
VERBS = {None: "수정된", "편성": "편성된", "훈련 기록": "훈련 기록이 수정된", "결재": "결재된"}
RECALCULATE = "training.recalculate."
NOT_EDITS = ("training.recalculate.initial_backfill",)
SHOWN = 10


class ChangedPeopleArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")

	period: Period = Field(default="오늘", description="수정된 시점. 오늘·어제·이번 주·최근 7일·이번 달")
	kind: ChangeKind | None = Field(
		default=None, description="수정 종류. 편성=편성·해제·재편성, 훈련 기록=출석·결과 수정, 결재=보류·연기 승인. 말하지 않으면 모두")


@dataclass
class Change:
	kinds: set[str] = field(default_factory=set)
	last_at: datetime | None = None  # 변경 기록은 UTC(시간대 없음)로 저장된다.


def label_for(period: str, kind: str | None) -> str:
	return f"{period} {VERBS[kind]} 인원"


def parse_label(label: str) -> tuple[str, str | None] | None:
	"""label_for의 반대: "오늘 편성된 인원" → ("오늘", "편성"). 이 형식이 아니면 None."""
	for kind, verb in VERBS.items():
		suffix = f" {verb} 인원"
		if label.endswith(suffix):
			return label.removesuffix(suffix), kind
	return None


def window(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
	"""한국 날짜 기준 기간 → 변경 기록과 같은 UTC(시간대 없음) 구간 [시작, 끝)."""
	now = now or datetime.now(KST)
	today = now.replace(hour=0, minute=0, second=0, microsecond=0)
	tomorrow = today + timedelta(days=1)
	start = {
		"오늘": today,
		"어제": today - timedelta(days=1),
		"이번 주": today - timedelta(days=today.weekday()),  # 월요일부터
		"최근 7일": today - timedelta(days=6),
		"이번 달": today.replace(day=1),
	}[period]
	end = today if period == "어제" else tomorrow
	return tuple(moment.astimezone(timezone.utc).replace(tzinfo=None) for moment in (start, end))  # type: ignore[return-value]


def _people_in(row: AuditLog) -> list[tuple[str, str]]:
	"""변경 기록 한 줄이 가리키는 (군번, 수정 종류)."""
	if row.action.startswith(RECALCULATE) and row.action not in NOT_EDITS:
		return [(row.entity_key, TRAINING)] if row.entity_key else []
	try:
		detail = json.loads(row.detail) if row.detail else None
	except json.JSONDecodeError:
		return []
	if isinstance(detail, list):
		return [(str(item["military_number"]), ASSIGNMENT) for item in detail if isinstance(item, dict) and "military_number" in item]
	return []


def changed_people(db: Session, period: str | None, now: datetime | None = None, kind: str | None = None) -> dict[str, Change]:
	"""기간(None이면 전체) 안에 수정된 군번 → 수정 종류·마지막 시각. kind를 주면 그 종류만."""
	start, end = window(period, now) if period is not None else (None, None)
	audit = select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)
	approvals = select(Postponement).where(Postponement.status == "approved", Postponement.approved_at.is_not(None))
	if start is not None:
		audit = audit.where(AuditLog.created_at >= start, AuditLog.created_at < end)
		approvals = approvals.where(Postponement.approved_at >= start, Postponement.approved_at < end)

	found: dict[str, Change] = {}

	def add(number: str, name: str, moment: datetime | None) -> None:
		if kind is not None and name != KIND_NAMES[kind]:
			return
		change = found.setdefault(number, Change())
		change.kinds.add(name)
		if change.last_at is None or (moment is not None and moment > change.last_at):
			change.last_at = moment

	for row in db.scalars(audit):
		for number, name in _people_in(row):
			add(number, name, row.created_at)
	for row in db.scalars(approvals):
		add(row.person_id, APPROVAL, row.approved_at)
	return found


def clock(moment: datetime | None) -> str:
	if moment is None:
		return ""
	return moment.replace(tzinfo=timezone.utc).astimezone(KST).strftime("%m/%d %H:%M")


def list_changed_people(db: Session, args: ChangedPeopleArgs) -> ToolResult:
	found = changed_people(db, args.period, kind=args.kind)
	people = {person.military_number: person for person in db.scalars(
		select(Person).where(Person.military_number.in_(list(found)))).all()} if found else {}
	rows = sorted(((number, change) for number, change in found.items() if number in people),
		key=lambda pair: pair[1].last_at or datetime.min, reverse=True)
	label = label_for(args.period, args.kind)
	chips = [args.period, args.kind or "수정"]
	if not rows:
		latest = changed_people(db, None, kind=args.kind)
		last = max((change.last_at for change in latest.values() if change.last_at), default=None)
		hint = f" 마지막 기록은 {clock(last)}이에요." if last else ""
		return ToolResult(f"{label}{josa(label, '이', '가')} 없어요.{hint}", conditions=chips)

	by_kind = {name: sum(name in change.kinds for _, change in rows) for name in KIND_NAMES.values()}
	summary = " · ".join(f"{name} {count}명" for name, count in by_kind.items() if count)
	lines = [f"· {people[number].name}({number}) — {', '.join(sorted(change.kinds))} · {clock(change.last_at)}"
		for number, change in rows[:SHOWN]]
	more = f"\n외 {len(rows) - SHOWN}명은 인원 목록에 필터로 걸어 두었어요." if len(rows) > SHOWN else ""
	return ToolResult(
		f"{label}{josa(label, '은', '는')} {len(rows)}명이에요. ({summary})\n" + "\n".join(lines) + more
		+ "\n(시스템 자동 재계산과 조회 기록은 뺐어요.)",
		# 이 라벨로 "이 명단 엑셀로"가 수정 내용·시각을 담아 내보낸다(router._export_target).
		[UiAction(type="navigate", tab="roster", subtab="people"),
		 UiAction(type="filter", tab="roster", label=label, ids=[number for number, _ in rows])],
		conditions=chips,
	)
