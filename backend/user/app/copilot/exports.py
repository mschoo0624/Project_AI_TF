"""Read-only Copilot tool: 명단·신청 목록을 Excel에서 바로 열리는 CSV로 내보낸다.

DB는 바꾸지 않는다. 파일은 서버 메모리에 잠깐(TTL_SECONDS)만 두고, 답변에 붙는 [내려받기]로만 받을 수 있다.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Literal
from urllib.parse import quote

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.approvals import TYPE_NAMES, PendingPostponementsArgs, pending_items
from user.app.copilot.changes import ChangeKind, Period, changed_people, clock, label_for
from user.app.copilot.common import ToolResult, josa, squad_label
from user.app.copilot.filters import PersonFilter, resolve_people
from user.app.copilot.insights import KST
from user.app.copilot.schemas import Download
from user.app.models.person import Person
from user.app.services.assignment import personnel_category

TTL_SECONDS = 15 * 60
MAX_FILES = 20
MAX_ROWS = 5000
DOWNLOAD_PATH = "/copilot/downloads"

_files: OrderedDict[str, tuple[str, bytes, float, int]] = OrderedDict()  # 파일 이름, 내용, 만료 시각, 건수
_lock = threading.Lock()


class ExportArgs(PersonFilter):
	"""조건은 PersonFilter 그대로. 결재 대기 신청 목록도 내보낼 수 있다."""

	subject: Literal["members", "pending_postponements", "changed_people"] = Field(
		default="members",
		description="members=인원 명단, pending_postponements=결재 대기 보류·연기 신청, changed_people=기간 안에 수정된 인원")
	period: Period | None = Field(default=None, description="수정된 시점 (changed_people일 때). 오늘·어제·이번 주·최근 7일·이번 달")
	change_kind: ChangeKind | None = Field(default=None, description="수정 종류 (changed_people일 때). 편성·훈련 기록·결재. 없으면 모두")
	kind: Literal["보류", "연기"] | None = Field(default=None, description="신청 종류 (pending_postponements일 때)")
	incomplete_documents: bool = Field(default=False, description="서류가 없거나 부족한 신청만 (pending_postponements일 때)")
	# 조건 없이 전체 인원. LLM이 조건을 놓치고 전체를 내보내지 못하게, 규칙이 "전체 인원 엑셀로"를 읽었을 때만 켠다.
	everyone: SkipJsonSchema[bool] = False
	# 직전 답변의 명단("이 명단 엑셀로"). LLM에는 보이지 않고 라우터가 채운다.
	military_numbers: SkipJsonSchema[list[str] | None] = None
	scope_label: SkipJsonSchema[str | None] = None


# ---------------------------------------------------------------- 파일 보관

def _cell(value: object) -> str:
	text = "" if value is None else str(value)
	# Excel이 수식으로 실행하지 못하게 한다. 신청 사유처럼 문서에서 온 글자가 들어갈 수 있다.
	return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(headers: list[str], rows: list[list[object]]) -> bytes:
	buffer = io.StringIO()
	writer = csv.writer(buffer, lineterminator="\r\n")
	writer.writerow(headers)
	writer.writerows([_cell(value) for value in row] for row in rows)
	return buffer.getvalue().encode("utf-8-sig")  # BOM이 있어야 Excel이 한글을 깨뜨리지 않는다.


def store(filename: str, headers: list[str], rows: list[list[object]]) -> Download:
	now = time.monotonic()
	token = secrets.token_urlsafe(16)
	with _lock:
		for key in [key for key, (_, _, expires, _) in _files.items() if expires <= now]:
			del _files[key]
		while len(_files) >= MAX_FILES:
			_files.popitem(last=False)
		_files[token] = (filename, to_csv(headers, rows), now + TTL_SECONDS, len(rows))
	return Download(url=f"{DOWNLOAD_PATH}/{token}", filename=filename, rows=len(rows))


def lookup(token: str) -> tuple[str, bytes, int] | None:
	"""(파일 이름, 내용, 건수). 없거나 15분이 지났으면 None."""
	with _lock:
		found = _files.get(token)
		if found is None or found[2] <= time.monotonic():
			_files.pop(token, None)
			return None
		return found[0], found[1], found[3]


def fetch(token: str) -> tuple[str, bytes] | None:
	found = lookup(token)
	return (found[0], found[1]) if found else None


def content_disposition(filename: str) -> str:
	return f"attachment; filename=\"export.csv\"; filename*=UTF-8''{quote(filename)}"


def _filename(label: str) -> str:
	safe = re.sub(r'[\\/:*?"<>|\s]+', "_", label).strip("_") or "명단"
	return f"{safe[:40]}_{datetime.now(KST):%Y%m%d}.csv"


# ---------------------------------------------------------------- 도구

def _done(label: str, headers: list[str], rows: list[list[object]], chips: list[str]) -> ToolResult:
	download = store(_filename(label), headers, rows)
	return ToolResult(
		f"{label} {len(rows)}건을 CSV 파일로 만들었어요. 아래 [내려받기]를 누르면 받을 수 있고, Excel에서 바로 열려요. "
		f"(파일은 {TTL_SECONDS // 60}분 동안만 보관돼요. 개인정보가 들어 있으니 필요한 곳에만 쓰세요.)",
		conditions=chips, download=download)


def _members(db: Session, args: ExportArgs, extra_columns: tuple[list[str], dict[str, list[object]]] | None = None) -> ToolResult:
	resolved = None
	if args.military_numbers is not None:
		chosen = set(args.military_numbers)
		people = list(db.scalars(select(Person).where(Person.military_number.in_(chosen))).all())
		if not args.is_empty():
			allowed = {person.military_number for person in resolve_people(db, args.conditions()).people}
			people = [person for person in people if person.military_number in allowed]
		label = args.scope_label or "직전 명단"
		chips = [label, *args.conditions().labels()]
		# 직전 답변이 교육 미달자·고발 검토 대상 명단이었으면 직접 요청했을 때와 같은 열(이수 시간·사유)을 넣는다.
		training = args.training or ("shortfall" if "교육 미달" in label else "prosecution" if "고발" in label else None)
		if training:
			resolved = resolve_people(db, PersonFilter(training=training))
	else:
		resolved = resolve_people(db, args.conditions())
		if resolved.question:
			return ToolResult(resolved.question)
		condition = resolved.applied or args
		people = resolved.people
		label = " ".join(condition.labels(with_training=False)) or "전체 인원"
		chips = condition.labels()
		training = condition.training
	if not people:
		if args.name and args.military_numbers is None:
			# '결제한'처럼 조건을 말한 단어를 이름으로 읽었을 수 있다. 없는 이름 때문에 빈 답만 주지 않는다.
			return ToolResult(f"이름이나 군번이 '{args.name}'인 인원이 없어서 파일을 만들지 않았어요. 사람 이름이 아니라 조건을 말씀하신 거라면 "
				"다르게 표현해 주세요. 예: \"오늘 편성한 인원 엑셀로 줘\", \"오늘 결재한 인원 엑셀로 줘\", \"교육 미달자 엑셀로 줘\"", conditions=chips)
		return ToolResult(f"{label} 조건에 맞는 인원이 없어서 파일을 만들지 않았어요.", conditions=chips)
	if len(people) > MAX_ROWS:
		return ToolResult(f"{label}{len(people)}명은 한 번에 내보내기엔 많아요. 조건을 좁혀 주세요.", conditions=chips)

	people.sort(key=lambda person: person.military_number)
	squads: dict[int, str] = {}
	headers = ["군번", "이름", "군별", "계급", "구분", "연차", "직책", "소속", "동원 상태"]
	extra: list[str] = []
	if training == "shortfall":
		extra = ["필요 시간", "이수 시간", "남은 시간", "이월 시간"]
	elif training == "prosecution":
		extra = ["고발 검토 사유"]
	rows: list[list[object]] = []
	for person in people:
		if person.squad_id is not None and person.squad_id not in squads:
			squads[person.squad_id] = squad_label(db, person.squad_id)
		row: list[object] = [
			person.military_number, person.name, person.branch, person.rank, personnel_category(person.rank),
			person.service_year, person.position, squads.get(person.squad_id, "미편성") if person.squad_id is not None else "미편성",
			person.mobilization_status,
		]
		if resolved is not None and extra:
			hours = resolved.hours.get(person.military_number)
			if training == "shortfall":
				row += [hours.required, hours.completed, hours.remaining, hours.carryover] if hours else ["", "", "", ""]
			else:
				row += [resolved.reasons.get(person.military_number, "")]
		elif extra:
			row += [""] * len(extra)
		if extra_columns is not None:
			row += extra_columns[1].get(person.military_number, [""] * len(extra_columns[0]))
		rows.append(row)
	return _done(label, headers + extra + (extra_columns[0] if extra_columns else []), rows, chips)


def _changed(db: Session, args: ExportArgs) -> ToolResult:
	"""기간 안에 수정된 인원. 어떤 수정이었고 언제였는지 열로 같이 담는다."""
	period = args.period or "오늘"
	found = changed_people(db, period, kind=args.change_kind)
	label = label_for(period, args.change_kind)
	chips = [period, args.change_kind or "수정"]
	ids = sorted(found)
	if not ids:
		return ToolResult(f"{label}{josa(label, '이', '가')} 없어서 파일을 만들지 않았어요.", conditions=chips)
	extras = {number: [", ".join(sorted(change.kinds)), clock(change.last_at)] for number, change in found.items()}
	result = _members(db, ExportArgs(military_numbers=ids, scope_label=label), (["수정 내용", "마지막 수정"], extras))
	result.conditions = chips
	return result


def _pending(db: Session, args: ExportArgs) -> ToolResult:
	items, people = pending_items(db, PendingPostponementsArgs(kind=args.kind, incomplete_documents=args.incomplete_documents))
	scope = f"{args.kind} " if args.kind else "보류·연기 "
	label = f"{'서류 미비 ' if args.incomplete_documents else ''}결재 대기 {scope}신청".replace("  ", " ").strip()
	chips = ["결재 대기", *([args.kind] if args.kind else []), *(["서류 미비"] if args.incomplete_documents else [])]
	if not items:
		return ToolResult(f"{label}이 없어서 파일을 만들지 않았어요.", conditions=chips)
	rows = []
	for row, state, missing in items:
		person = people.get(row.person_id)
		rows.append([row.person_id, person.name if person else "", TYPE_NAMES.get(row.type, row.type), row.training_year,
			(row.reason or "").strip(), state, ", ".join(missing), row.source_file or ""])
	return _done(label, ["군번", "이름", "구분", "훈련 연도", "신청 사유", "서류 상태", "부족한 항목", "제출 파일"], rows, chips)


def export_list(db: Session, args: ExportArgs) -> ToolResult:
	if args.subject == "pending_postponements":
		return _pending(db, args)
	return _changed(db, args) if args.subject == "changed_people" else _members(db, args)
