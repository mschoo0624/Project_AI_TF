"""Read-only Copilot tool: 보고용 현황 초안.

오늘 현황 숫자(insights.collect_status)와 결재 대기·서류 미비를 모아 복사해서 쓸 수 있는 보고 문안으로 정리한다.
숫자는 DB에서 그대로 가져오고 문장은 양식 파일(report_template.txt)이라 AI가 숫자를 지어내지 않는다. 담당자가 검토 후 사용한다.
양식은 파일만 고치면 바뀐다(서버를 다시 켤 필요 없음). 파일이 없거나 깨져 있으면 아래 기본 양식을 쓴다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.approvals import INCOMPLETE, _document_state
from user.app.copilot.common import ToolResult
from user.app.copilot.insights import KST, collect_status
from user.app.models.postpoment import Postponement

logger = logging.getLogger(__name__)

WEEKDAYS = "월화수목금토일"
TEMPLATE_PATH = Path(__file__).with_name("report_template.txt")
# 양식 파일을 못 읽을 때 쓰는 기본 양식 (파일 내용과 같다).
DEFAULT_TEMPLATE = """[예비군 현황 보고] {date} 기준

1. 인원 현황
  - 전체 {total}명 (복무 중 {active}명)
  - 편성 대상 중 미편성 {unassigned}명
  - 보류 상태 {held}명 (승인된 보류 {approved_hold}명, 승인된 연기 {approved_delay}명)

2. 교육 현황
  - 올해 교육 대상 {targets}명 중 이수 {done}명({done_pct}), 미달 {short}명
  - 고발 검토 대상 {prosecution}명

3. 결재 현황
  - 보류·연기 신청 결재 대기 {pending_postponements}건 (서류 미비 {incomplete_documents}건)
  - 전입 확인 대기 {pending_transfers}건

4. 특이사항
  - {issues}"""


class StatusReportArgs(BaseModel):
	model_config = ConfigDict(extra="forbid")


class _Known(dict):
	"""양식에 없는 자리 표시는 {이름} 그대로 남긴다(오타를 눈에 띄게)."""

	def __missing__(self, key: str) -> str:
		return "{" + key + "}"


def _percent(part: int, whole: int) -> str:
	return f"{part / whole * 100:.1f}%" if whole else "-"


def _template() -> tuple[str, str]:
	"""(양식, 안내). 파일을 읽을 수 있으면 파일, 아니면 기본 양식."""
	try:
		lines = TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
	except OSError:
		return DEFAULT_TEMPLATE, "양식 파일(report_template.txt)을 읽지 못해 기본 양식을 썼어요."
	body = "\n".join(line for line in lines if not line.lstrip().startswith("#")).strip("\n")
	if not body.strip():
		return DEFAULT_TEMPLATE, "양식 파일(report_template.txt)이 비어 있어 기본 양식을 썼어요."
	return body, ""


def draft_status_report(db: Session, args: StatusReportArgs) -> ToolResult:
	snap = collect_status(db)
	now = datetime.now(KST)
	pending = list(db.scalars(select(Postponement).where(Postponement.status == "pending")).all())
	done = len(snap.targets) - len(snap.short)
	approved = snap.approved_by_type
	values = _Known(
		date=f"{now.year}. {now.month}. {now.day}.({WEEKDAYS[now.weekday()]})",
		total=len(snap.people), active=len(snap.active), unassigned=len(snap.unassigned), held=len(snap.held),
		approved_hold=approved.get("보류", 0), approved_delay=approved.get("연기", 0),
		targets=len(snap.targets), done=done, done_pct=_percent(done, len(snap.targets)), short=len(snap.short),
		prosecution=len(snap.prosecution), pending_postponements=snap.pending_postponements,
		incomplete_documents=sum(1 for row in pending if _document_state(row)[0] in INCOMPLETE),
		pending_transfers=snap.pending_transfers,
		issues=(f"이상 데이터 {len(snap.issues)}종류: " + ", ".join(issue.title for issue in snap.issues)
			if snap.issues else "이상 데이터 없음"),
	)
	template, notice = _template()
	try:
		text = template.format_map(values)
	except (ValueError, IndexError, KeyError, AttributeError):
		# 양식에 짝이 안 맞는 중괄호처럼 문법이 틀린 곳이 있다. 보고가 막히지 않게 기본 양식으로 대신한다.
		logger.warning("보고서 양식을 적용하지 못해 기본 양식을 씁니다", exc_info=True)
		text, notice = DEFAULT_TEMPLATE.format_map(values), "양식 파일에 문법이 틀린 곳이 있어 기본 양식을 썼어요."
	footer = "위 문안은 현재 DB 기준입니다. 보고 전에 내용을 확인해 주세요."
	return ToolResult(text + "\n\n" + (notice + " " if notice else "") + footer, conditions=["보고용"])
