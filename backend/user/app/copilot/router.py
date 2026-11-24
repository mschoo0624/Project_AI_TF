"""POST /copilot/chat: rule router → LLM tool choice → tool → template answer."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from functools import partial
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from user.app.copilot import briefing, changes, exports, followups, history, llm
from user.app.copilot.common import josa, squad_label
from user.app.copilot.exports import ExportArgs
from user.app.copilot.filters import PersonFilter
from user.app.copilot.rules import Unparsed, refers_to_previous, route
from user.app.copilot.schemas import (
	CLIENT_ID_PATTERN, ApplyRequest, ApplyResponse, ChatRequest, ChatResponse, ConversationDetail, ConversationSummary,
	UndoPreview, UndoRequest, UndoResponse, UndoSkipView, UndoStepView,
)
from user.app.copilot.tools import TOOLS, BulkAssignmentArgs, MoveArgs, ReleaseArgs, TransferSquadArgs
from user.app.database import get_db
from user.app.models.audit_log import AuditLog
from user.app.models.copilot import CopilotMessage
from user.app.models.user import User
from user.app.services.assignment import confirm_assignment_selections, reassign_person
from user.app.services.audit import change_source
from user.app.services.auth import get_current_user
from user.app.services.organization import release_members, root_node_id
from user.app.services.undo import UndoPlan, apply_undo, plan_undo

router = APIRouter(prefix="/copilot", tags=["copilot"])
logger = logging.getLogger(__name__)

HELP = (
	"이런 걸 도와드릴 수 있어요.\n"
	"· 인원 찾기: \"1소대 육군 간부 보여줘\", \"미편성 전입자 명단\"\n"
	"· 편성: \"방금 등록한 전입자 어디 편성하면 돼?\", \"미편성 인원들 편성해줘\"\n"
	"· 재편성: \"정태윤 재편성해줘\", \"정태윤은 1소대에 있으면 안 돼. 다른 데로 옮겨줘\"\n"
	"· 편성 해제: \"0년차 편성된 사람 빼줘\", \"1소대 3분대 비워줘\"\n"
	"· 현황·조회: \"오늘 현황\", \"홍길동 정보\", \"교육 미달자 보여줘\", \"고발 대상자 보여줘\"\n"
	"· 결재: \"결재 대기 목록 보여줘\", \"서류가 빠진 연기 신청은?\"\n"
	"· 보고: \"오늘 현황 보고용으로 정리해줘\"\n"
	"· 내보내기: \"서류가 빠진 신청 엑셀로 줘\", \"교육 미달자 엑셀로 줘\", (명단을 본 뒤) \"이 명단 엑셀로 줘\"\n"
	"· 수정한 인원: \"오늘 수정한 인원 보여줘\", \"이번 주 수정한 인원 엑셀로 줘\"\n"
	"· 점검: \"이상 데이터 점검해줘\", \"최근 변경 기록\""
)


@dataclass
class Turn:
	"""One answer plus how it was reached, for the question log."""

	response: ChatResponse
	outcome: Literal["answered", "asked_back", "not_understood", "error"]
	args: BaseModel | None = None
	used_context: bool = False


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
	"""Answer, then save the question and answer to the conversation. Saving never blocks the answer."""
	trace_id = uuid.uuid4().hex[:12]
	started = time.perf_counter()
	try:
		turn = _answer(payload, db, trace_id)
	except Exception:
		db.rollback()
		_save(db, payload, Turn(ChatResponse(message="처리 중 오류가 났어요.", routed_by="none", trace_id=trace_id), "error"), started)
		raise
	_save(db, payload, turn, started)
	return turn.response


def _save(db: Session, payload: ChatRequest, turn: Turn, started: float) -> None:
	try:
		history.save_turn(db, payload, turn.response, outcome=turn.outcome, args=turn.args,
			used_context=turn.used_context, latency_ms=round((time.perf_counter() - started) * 1000))
	except Exception:
		db.rollback()
		logger.exception("Copilot 대화를 저장하지 못했습니다 (trace_id=%s)", turn.response.trace_id)


def _answer(payload: ChatRequest, db: Session, trace_id: str) -> Turn:
	# 같은 대화의 후속 질문("그럼 2소대는?")이면 앞 조회의 조건을 이어받는다.
	followup = followups.resolve(db, payload)
	if followup is not None and followup.ask_back:
		return Turn(ChatResponse(message=followup.ask_back, routed_by="rule", trace_id=trace_id), "asked_back")
	inherited = followup is not None and followup.routed is not None and followup.routed[0] == "search_members"
	routed = followup.routed if followup is not None else route(payload.message)
	routed_by = "rule"
	if isinstance(routed, Unparsed) and routed.question:
		return Turn(ChatResponse(message=routed.question, unparsed=routed.words, routed_by="rule", trace_id=trace_id),
			"asked_back")
	if routed is None or isinstance(routed, Unparsed):
		unparsed = routed
		routed_by = "llm"
		try:
			choice = llm.choose_tool(payload.message)
		except (llm.LLMUnavailable, KeyError, json.JSONDecodeError) as error:
			if unparsed is not None:
				# 일부만 이해했다고 조건을 빼고 답하지 않는다. 무엇을 못 알아들었는지 말한다.
				words = ", ".join(f"'{word}'" for word in unparsed.words)
				return Turn(ChatResponse(
					message=f"{words}{josa(unparsed.words[-1], '은', '는')} 아직 조건으로 이해하지 못했어요. 이 말을 빼거나 "
						f"다르게 표현해 주세요. (AI 해석을 쓸 수 없어서 규칙으로만 처리했어요: {error})",
					unparsed=unparsed.words, routed_by="none", trace_id=trace_id,
				), "not_understood")
			return Turn(ChatResponse(message=f"{HELP}\n(규칙으로 처리하지 못했고, {error})", routed_by="none",
				trace_id=trace_id), "not_understood")
		if choice is None or choice[0] not in TOOLS:
			return Turn(ChatResponse(message=HELP, routed_by="llm", trace_id=trace_id), "not_understood")
		name, raw_args = choice
		if name == "export_list" and unparsed is not None:
			# 규칙이 못 알아들은 말("오늘 수정한")을 LLM이 버리고 전체를 내보내면 개인정보가 조건 없이 나간다.
			words = ", ".join(f"'{word}'" for word in unparsed.words)
			return Turn(ChatResponse(
				message=f"{words}{josa(unparsed.words[-1], '은', '는')} 아직 조건으로 이해하지 못했어요. 파일에는 개인정보가 들어 있어서 "
					"조건을 정확히 알 때만 만들어요. 다르게 말씀해 주세요. 예: \"교육 미달자 엑셀로 줘\", \"서류가 빠진 신청 엑셀로 줘\"",
				unparsed=unparsed.words, tool=name, routed_by="llm", trace_id=trace_id,
			), "not_understood")
		try:
			routed = name, TOOLS[name].args_model.model_validate(raw_args)
		except ValidationError:
			return Turn(ChatResponse(
				message="요청 조건을 정확히 이해하지 못했어요. 소대·군별·계급을 다시 말씀해 주세요. 예: \"2소대 해군 병사 보여줘\"",
				tool=name, routed_by="llm", trace_id=trace_id,
			), "not_understood")

	name, args = routed
	used_context = inherited
	if name == "propose_move" and isinstance(args, MoveArgs) and not (args.name or args.military_number):
		# 이름 없이 "재편성해줘": 직전 답변이 한 사람을 보여줬으면 그 사람이다.
		context = payload.context
		if context is None or len(context.ids) != 1:
			return Turn(ChatResponse(
				message="누구를 재편성할지 이름이나 군번을 알려 주세요. 예: \"정태윤 재편성해줘\"",
				tool=name, routed_by=routed_by, trace_id=trace_id,
			), "asked_back", args)
		args = args.model_copy(update={"military_number": context.ids[0]})
		used_context = True
	if name in ("propose_bulk_assignment", "recommend_squad_for_transfer", "propose_release") and refers_to_previous(payload.message):
		# "저 인원들 편성해줘": 직전 답변의 명단만 대상으로 한다.
		context = payload.context
		if context is None or not context.ids:
			return Turn(ChatResponse(
				message="어떤 인원을 말씀하시는지 모르겠어요. 먼저 명단을 조회하거나 조건을 함께 말씀해 주세요. 예: \"미편성 전입자 편성해줘\"",
				tool=name, routed_by=routed_by, trace_id=trace_id,
			), "asked_back", args)
		used_context = True
		# 함께 말한 조건("저 인원들 중 0년차 빼줘")은 유지하고 대상만 직전 명단으로 좁힌다.
		conditions = args.conditions().model_dump(exclude_defaults=True) if isinstance(args, PersonFilter) else {}
		conditions.pop("assigned", None)
		if name == "propose_release":
			args = ReleaseArgs(**conditions, military_numbers=context.ids, scope_label=context.label)
		elif len(context.ids) == 1 and not conditions:
			name, args = "recommend_squad_for_transfer", TransferSquadArgs(military_number=context.ids[0])
		else:
			name, args = "propose_bulk_assignment", BulkAssignmentArgs(
				**conditions, military_numbers=context.ids, scope_label=context.label)
	if name == "export_list" and isinstance(args, ExportArgs) and args.subject == "members" and not args.everyone \
			and (refers_to_previous(payload.message) or args.is_empty()):
		# "이 명단 엑셀로 줘", "엑셀로 줘": 직전 답변이 보여준 명단을 내보낸다.
		context = payload.context
		if context is None or not context.ids:
			return Turn(ChatResponse(
				message="어떤 명단을 내보낼지 모르겠어요. 먼저 명단을 조회하거나 조건을 함께 말씀해 주세요. "
					"예: \"교육 미달자 엑셀로 줘\", \"전체 인원 엑셀로 줘\"",
				tool=name, routed_by=routed_by, trace_id=trace_id,
			), "asked_back", args)
		args = _export_target(args, context.label, context.ids)
		used_context = True
	result = TOOLS[name].run(db, args)
	return Turn(ChatResponse(
		message=result.message,
		ui_actions=result.ui_actions,
		proposal=result.proposal,
		download=result.download,
		conditions=result.conditions,
		tool=name,
		routed_by=routed_by,
		trace_id=trace_id,
	), "answered", args, used_context)


def _export_target(args: ExportArgs, label: str, ids: list[str]) -> ExportArgs:
	"""직전 답변이 결재 신청 목록이었으면 그 신청을, 아니면 그 인원 명단을 내보낸다."""
	changed = changes.parse_label(label)  # changes.list_changed_people이 붙인 라벨: "오늘 수정된 인원", "오늘 편성된 인원"
	if changed is not None:
		return ExportArgs(subject="changed_people", period=changed[0], change_kind=changed[1])
	if "결재 대기" in label:
		return ExportArgs(
			subject="pending_postponements",
			kind="연기" if "연기" in label and "보류" not in label else "보류" if "보류" in label and "연기" not in label else None,
			incomplete_documents="서류 미비" in label,
		)
	return args.model_copy(update={"military_numbers": ids, "scope_label": label})


@router.get("/downloads/{token}")
def download(token: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
	"""채팅 답변의 [내려받기]. 파일은 만든 지 15분 안에만 받을 수 있고, 받을 때마다 변경 기록에 남는다."""
	found = exports.lookup(token)
	if found is None:
		raise HTTPException(status_code=404, detail="내려받기 기간이 지났어요. 다시 요청해 주세요.")
	filename, content, rows = found
	# 개인정보가 든 파일이라 누가 언제 몇 건을 받았는지 남긴다. 기록에는 이름·군번 같은 내용은 넣지 않는다.
	# summary를 비워 둬서 "최근 변경 기록"(편성 변경)에는 나오지 않는다. 기록하지 못하면 파일도 주지 않는다.
	db.add(AuditLog(user_id=user.id, action="copilot.export.download", table_name="copilot_export",
		actor_label=user.username, source="copilot", after_data=json.dumps({"filename": filename, "rows": rows}, ensure_ascii=False)))
	db.commit()
	return Response(content, media_type="text/csv; charset=utf-8", headers={
		"Content-Disposition": exports.content_disposition(filename), "Cache-Control": "no-store"})


@router.get("/briefing", response_model=briefing.Briefing)
def get_briefing(client_id: str | None = Query(default=None, pattern=CLIENT_ID_PATTERN),
		db: Session = Depends(get_db)) -> briefing.Briefing:
	"""채팅을 열면 먼저 보여 주는 오늘 확인할 일. client_id를 주면 이 브라우저의 지난 대화에서 기억한 것도 담는다. 조회만 한다."""
	return briefing.build_briefing(db, client_id)


@router.post("/apply", response_model=ApplyResponse)
def apply(payload: ApplyRequest, db: Session = Depends(get_db)) -> ApplyResponse:
	"""[승인]을 누른 제안만 실행한다. 변경은 기존 서비스가 검증하고, 변경 기록에 copilot으로 남는다."""
	# 다시 연 대화의 카드를 또 승인하지 않게 한다. 한 카드는 한 번만 실행된다.
	if history.already_applied(db, payload.trace_id):
		raise HTTPException(status_code=409, detail="이미 승인한 제안입니다.")
	try:
		with change_source("copilot", payload.trace_id):
			message = _apply(payload, db)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	history.mark_applied(db, payload.trace_id, message)
	return ApplyResponse(message=message)


def _apply(payload: ApplyRequest, db: Session) -> str:
	if payload.kind == "move":
		if len(payload.assignments) != 1:
			raise ValueError("옮길 인원과 분대를 하나 골라 주세요.")
		target = payload.assignments[0]
		moved = reassign_person(db, target.person_id, target.squad_id)
		return f"{moved['name']}을(를) 옮겼습니다."
	if payload.kind in ("assign_squad", "assign_bulk"):
		if not payload.assignments:
			raise ValueError("편성할 인원이 없습니다.")
		result = confirm_assignment_selections(
			db, ((item.person_id, item.squad_id) for item in payload.assignments))
		return f"{result['total_assigned']}명을 편성했습니다."
	root_id = root_node_id(db)
	if root_id is None or not payload.person_ids:
		raise ValueError("해제할 인원이 없습니다.")
	result = release_members(db, root_id, person_ids=payload.person_ids)
	return f"{result['released_count']}명의 편성을 해제했습니다."


def _undoable(db: Session, trace_id: str, client_id: str) -> CopilotMessage:
	message = history.owned_message(db, trace_id, client_id)
	if message is None:
		raise HTTPException(status_code=404, detail="이 대화의 제안을 찾을 수 없습니다.")
	if message.applied_at is None:
		raise HTTPException(status_code=409, detail="승인하지 않은 제안이라 되돌릴 변경이 없습니다.")
	return message


def _nothing_left(message: CopilotMessage, plan: UndoPlan) -> None:
	"""한 번 되돌렸어도 남은 인원이 있으면 마저 되돌릴 수 있다."""
	if message.undone_at is not None and not plan.steps:
		raise HTTPException(status_code=409, detail="이미 되돌린 변경입니다.")


def _skipped(plan: UndoPlan) -> list[UndoSkipView]:
	return [UndoSkipView(person_id=item.military_number, name=item.name, reason=item.reason) for item in plan.skipped]


@router.get("/undo/{trace_id}", response_model=UndoPreview)
def preview_undo(trace_id: str, client_id: str = Query(pattern=CLIENT_ID_PATTERN), db: Session = Depends(get_db)) -> UndoPreview:
	"""되돌리면 누가 어디로 가는지, 누구를 왜 건너뛰는지. 아무것도 바꾸지 않는다."""
	message = _undoable(db, trace_id, client_id)
	label = partial(squad_label, db)
	plan = plan_undo(db, trace_id, label)
	_nothing_left(message, plan)
	return UndoPreview(
		steps=[
			UndoStepView(person_id=step.military_number, name=step.name,
				now=label(step.from_squad_id) if step.from_squad_id is not None else "미편성",
				after=label(step.to_squad_id) if step.to_squad_id is not None else "미편성")
			for step in plan.steps
		],
		skipped=_skipped(plan),
	)


@router.post("/undo/{trace_id}", response_model=UndoResponse)
def undo(trace_id: str, payload: UndoRequest, db: Session = Depends(get_db)) -> UndoResponse:
	"""미리 본 뒤 [되돌리기 확인]을 눌렀을 때. 그사이 데이터가 바뀌었을 수 있어 지금 데이터로 다시 계산한다."""
	message = _undoable(db, trace_id, payload.client_id)
	_nothing_left(message, plan_undo(db, trace_id, partial(squad_label, db)))
	try:
		with change_source("copilot", trace_id):
			plan = apply_undo(db, trace_id, partial(squad_label, db))
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	summary = (f"남은 {len(plan.steps)}명을 마저 되돌렸습니다." if plan.already else f"{len(plan.steps)}명을 되돌렸습니다.") 		+ (f" {len(plan.skipped)}명은 건너뛰었습니다." if plan.skipped else "")
	undone_at = history.mark_undone(db, message, summary)
	return UndoResponse(message=summary, undone_at=undone_at, skipped=_skipped(plan))


@router.get("/conversations", response_model=list[ConversationSummary])
def conversations(client_id: str = Query(pattern=CLIENT_ID_PATTERN), db: Session = Depends(get_db)) -> list[ConversationSummary]:
	"""이 브라우저의 대화 목록, 최근 순."""
	return history.list_conversations(db, client_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation(conversation_id: str, client_id: str = Query(pattern=CLIENT_ID_PATTERN),
		db: Session = Depends(get_db)) -> ConversationDetail:
	found = history.get_conversation(db, conversation_id, client_id)
	if found is None:
		raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
	return found


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, client_id: str = Query(pattern=CLIENT_ID_PATTERN),
		db: Session = Depends(get_db)) -> None:
	if not history.delete_conversation(db, conversation_id, client_id):
		raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
