"""PersonFilter: the one set of person conditions every list tool shares.

Search, bulk assignment and release all take a PersonFilter (their args subclass it),
and resolve_people() turns it into people. A new condition is added here once and
every tool understands it; labels() is what the answer shows as "조건" chips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.copilot.common import TRANSFER_REGISTRATION, Branch, Category, Rank, josa, squad_label
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.services.assignment import is_assignable
from user.app.services.person_search import PersonSearch, search_people, squad_ids_for_platoon
from user.app.services.training_summary import YearHours, current_year_hours, prosecution_reasons

Training = Literal["shortfall", "prosecution"]


class PersonFilter(BaseModel):
	model_config = ConfigDict(extra="forbid")

	platoon: str | None = Field(default=None, pattern=r"^\d{1,2}소대$", description="소대, 예: 1소대")
	squad: str | None = Field(default=None, pattern=r"^\d{1,2}분대$", description="분대, 예: 3분대")
	branch: Branch | None = None
	category: Category | None = Field(default=None, description="간부 = 부사관 + 장교")
	rank: Rank | None = None
	service_year: int | None = Field(default=None, ge=0, le=8, description="연차. 예: '0년차' → 0")
	assigned: bool | None = Field(default=None, description="true=편성된 인원, false=미편성 인원")
	not_assignable: bool = Field(default=False, description="편성 대상이 아닌 인원만(0년차·비활성·연차 미등록)")
	transfer_only: bool = Field(default=False, description="예비군 전입자만")
	training: Training | None = Field(
		default=None, description="shortfall=올해 교육 시간을 못 채운 인원, prosecution=고발 검토 대상자")
	name: str | None = Field(default=None, max_length=50, description="이름 또는 군번 일부")

	def conditions(self) -> PersonFilter:
		"""PersonFilter 필드만 남긴 복사본 (도구별 숨은 필드 제외)."""
		return PersonFilter(**{key: getattr(self, key) for key in PersonFilter.model_fields})

	def is_empty(self) -> bool:
		return not self.conditions().model_dump(exclude_defaults=True)

	def labels(self, with_training: bool = True) -> list[str]:
		# 편성 여부를 앞에 둬야 "미편성 병사", "편성된 0년차"처럼 자연스럽게 읽힌다.
		labels = ["편성된" if self.assigned is True else "미편성" if self.assigned is False else None,
			self.platoon, self.squad, self.branch, self.rank or self.category,
			f"{self.service_year}년차" if self.service_year is not None else None]
		if self.transfer_only:
			labels.append("전입자")
		if self.not_assignable:
			labels.append("편성 대상 아님")
		if with_training and self.training:
			labels.append("교육 미달" if self.training == "shortfall" else "고발 검토 대상")
		if self.name:
			labels.append(f"'{self.name}'")
		return [label for label in labels if label]


@dataclass
class Resolved:
	people: list[Person] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)
	# 사람을 찾기 전에 되물어야 하는 경우(모호한 분대, 없는 소대). 있으면 people은 비어 있다.
	question: str | None = None
	hours: dict[str, YearHours] = field(default_factory=dict)
	reasons: dict[str, str] = field(default_factory=dict)  # 고발 검토 사유
	applied: PersonFilter | None = None  # 실제로 적용한 조건 (예: 미편성이면 소대 조건은 뺀다)


def squad_scope(db: Session, platoon: str | None, squad: str) -> tuple[list[int], str] | str:
	"""'3분대'(+소대) → 분대 id들. 소대 없이 여러 곳에 있으면 되묻는 문장을 돌려준다."""
	nodes = list(db.scalars(select(OrganizationNode).where(OrganizationNode.kind == "squad", OrganizationNode.name == squad)).all())
	parents = {node.id: db.get(OrganizationNode, node.parent_id) if node.parent_id else None for node in nodes}
	if platoon:
		nodes = [node for node in nodes if parents[node.id] is not None and parents[node.id].name == platoon]
	if not nodes:
		return f"'{' '.join(part for part in (platoon, squad) if part)}'을 편제에서 찾지 못했어요."
	if len(nodes) > 1:
		where = ", ".join(parents[node.id].name for node in nodes[:6] if parents[node.id] is not None)
		return (f"{squad}{josa(squad, '은', '는')} 여러 소대에 있어요({where} …). "
			f"어느 소대인지 함께 말씀해 주세요. 예: \"1소대 {squad} …\"")
	return [node.squad_id for node in nodes if node.squad_id is not None], squad_label(db, nodes[0].squad_id)


def resolve_people(db: Session, condition: PersonFilter) -> Resolved:
	condition = condition.conditions()
	notes: list[str] = []
	if condition.assigned is False and (condition.platoon or condition.squad):
		# 미편성자는 분대가 없으므로 소속 소대·분대도 없다.
		dropped = " ".join(part for part in (condition.platoon, condition.squad) if part)
		notes.append(f"미편성 인원은 소대 소속이 없어서 '{dropped}' 조건은 뺐어요.")
		condition = condition.model_copy(update={"platoon": None, "squad": None})

	squad_ids: list[int] | None = None
	if condition.squad:
		scope = squad_scope(db, condition.platoon, condition.squad)
		if isinstance(scope, str):
			return Resolved(question=scope, applied=condition)
		squad_ids = scope[0]
	elif condition.platoon and not squad_ids_for_platoon(db, condition.platoon):
		return Resolved(question=f"'{condition.platoon}'을 조직도에서 찾지 못했어요. 소대 이름을 다시 확인해 주세요.",
			applied=condition)

	people = search_people(db, PersonSearch(
		query_text=condition.name,
		branch=condition.branch,
		rank=condition.rank,
		category=None if condition.rank else condition.category,
		platoon=None if squad_ids is not None else condition.platoon,
		assigned=condition.assigned,
		registration_type=TRANSFER_REGISTRATION if condition.transfer_only else None,
	))
	if squad_ids is not None:
		people = [person for person in people if person.squad_id in squad_ids]
	if condition.service_year is not None:
		people = [person for person in people if person.service_year == condition.service_year]
	if condition.not_assignable:
		people = [person for person in people if not is_assignable(person)]

	result = Resolved(people=people, notes=notes, applied=condition)
	if condition.training:
		result.hours = current_year_hours(db, people)
		if condition.training == "shortfall":
			result.people = sorted((person for person in people
				if person.military_number in result.hours and result.hours[person.military_number].remaining > 0),
				key=lambda person: -result.hours[person.military_number].remaining)
		else:
			result.reasons = prosecution_reasons(db, people, result.hours)
			result.people = [person for person in people if person.military_number in result.reasons]
	return result
