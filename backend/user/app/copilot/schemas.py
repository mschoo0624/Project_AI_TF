"""Copilot request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatContext(BaseModel):
	"""직전 답변이 보여준 명단. "저 인원들", "그 사람"이 가리키는 대상."""

	label: str = Field(max_length=100)
	ids: list[str] = Field(max_length=2000)


class ChatRequest(BaseModel):
	message: str = Field(min_length=1, max_length=500)
	context: ChatContext | None = None


class UiAction(BaseModel):
	"""Screen command the frontend runs in order. Never changes data."""

	type: Literal["navigate", "filter", "highlight"]
	tab: str
	subtab: str | None = None
	label: str | None = None
	ids: list[str] = Field(default_factory=list)


class SquadOption(BaseModel):
	squad_id: int
	squad_name: str
	current_count: int
	reason: str


class PlannedAssignment(BaseModel):
	person_id: str
	name: str
	squad_id: int
	squad_name: str


class Proposal(BaseModel):
	"""Approval card. On approval the frontend calls POST /copilot/apply.

	assign_squad: one person, the user picks one of `options`.
	assign_bulk: many people, `assignments` is approved as a whole.
	release: `assignments` lists people and their current squad; approval releases them.
	move: one assigned person, the user picks one of `options` to move them to (재편성).
	Copilot never adds squads; squads are created by hand on the organization screen.
	"""

	kind: Literal["assign_squad", "assign_bulk", "release", "move"]
	title: str
	person_id: str | None = None
	options: list[SquadOption] = Field(default_factory=list)
	assignments: list[PlannedAssignment] = Field(default_factory=list)
	notes: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
	message: str
	ui_actions: list[UiAction] = Field(default_factory=list)
	proposal: Proposal | None = None
	conditions: list[str] = Field(default_factory=list, description="적용한 조건. 화면에 칩으로 보인다.")
	unparsed: list[str] = Field(default_factory=list, description="규칙이 이해하지 못한 말")
	tool: str | None = None
	routed_by: Literal["rule", "llm", "none"]
	trace_id: str


class AssignmentSelection(BaseModel):
	person_id: str = Field(min_length=1, max_length=50)
	squad_id: int


class ApplyRequest(BaseModel):
	"""What the user approved on a proposal card."""

	kind: Literal["assign_squad", "assign_bulk", "release", "move"]
	trace_id: str | None = Field(default=None, max_length=32)
	assignments: list[AssignmentSelection] = Field(default_factory=list, max_length=2000)
	person_ids: list[str] = Field(default_factory=list, max_length=2000)


class ApplyResponse(BaseModel):
	message: str
