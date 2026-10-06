"""Shared pieces for Copilot tools: result types, Korean particles, squad labels."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.schemas import Proposal, UiAction
from user.app.models.organization import OrganizationNode
from user.app.models.squad import Squad

Branch = Literal["육군", "해군", "공군", "해병대"]
Category = Literal["병사", "부사관", "장교", "간부"]
Rank = Literal["이병", "일병", "상병", "병장", "하사", "중사", "상사", "원사", "소위", "중위", "대위", "소령", "중령", "대령"]
TRANSFER_REGISTRATION = "예비군 전입"


@dataclass
class ToolResult:
	message: str
	ui_actions: list[UiAction] = field(default_factory=list)
	proposal: Proposal | None = None
	conditions: list[str] = field(default_factory=list)  # 적용한 조건. 답변 위에 칩으로 보인다.


@dataclass(frozen=True)
class Tool:
	name: str
	description: str  # 한국어 한 문장: 언제 쓰는지
	args_model: type[BaseModel]
	kind: Literal["조회", "제안"]
	run: Callable[[Session, BaseModel], ToolResult]


def josa(word: str, with_final: str, without_final: str) -> str:
	"""받침에 맞는 조사: josa("병사", "은", "는") → "는"."""
	last = word.rstrip(" '\"‘’“”)")[-1:] or "가"  # "'정태윤'"은 따옴표가 아니라 '윤'으로 판단한다
	if "가" <= last <= "힣":
		return with_final if (ord(last) - ord("가")) % 28 else without_final
	return with_final if last.isdigit() and last in "013678" else without_final


def squad_label(db: Session, squad_id: int) -> str:
	"""'1소대 3분대' 형식. 조직도에 없으면 분대 이름을 그대로 쓴다."""
	node = db.scalar(select(OrganizationNode).where(OrganizationNode.squad_id == squad_id))
	if node is not None and node.parent_id is not None:
		parent = db.get(OrganizationNode, node.parent_id)
		if parent is not None and parent.kind == "platoon" and not node.name.startswith(parent.name):
			return f"{parent.name} {node.name}"
	squad = db.get(Squad, squad_id)
	return squad.name if squad is not None else f"{squad_id}번 분대"
