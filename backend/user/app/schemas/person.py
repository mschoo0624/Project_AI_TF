"""Person request and response schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

class PersonBase(BaseModel):
	name: str
	branch: str
	rank: str | None = None
	unit: str | None = None
	specialty: str | None = None
	origin_type: str | None = None
	registration_type: str | None = None
	service_year: int = Field(ge=0, le=99)
	discharge_date: date | None = None
	callup_release_date: date | None = None
	position: str
	mobilization_status: str = "해당없음"
	status: str = "active"
	squad_id: int | None = None

	@model_validator(mode="after")
	def validate_training_category(self) -> "PersonBase":
		if 1 <= self.service_year <= 4 and self.mobilization_status not in {
			"지정",
			"동원지정",
			"미지정",
			"동원미지정",
			"학생",
			"학생예비군",
			"보류",
			"일부보류",
			"훈련일부보류",
			"designated",
			"non_designated",
			"student",
			"partial_hold",
		}:
			raise ValueError("1-4 year reservists require a mobilization status")
		return self

class PersonCreate(PersonBase):
	military_number: str
	previous_training_hours: int | None = Field(
		default=None,
		description="이전 부대 이수 훈련 시간 (null이면 신규, > 0 이면 예비군 전입)",
	)

class PersonUpdate(BaseModel):
	name: str | None = None
	branch: str | None = None
	rank: str | None = None
	unit: str | None = None
	specialty: str | None = None
	origin_type: str | None = None
	service_year: int | None = Field(default=None, ge=0, le=99)
	discharge_date: date | None = None
	callup_release_date: date | None = None
	position: str | None = None
	mobilization_status: str | None = None
	status: str | None = None
	squad_id: int | None = None

class PersonProfileUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")
	military_number: str
	name: str
	unit: str
	branch: str
	status: str
	mobilization_status: str
	position: str
	specialty: str
	discharge_date: date | None = None
	callup_release_date: date | None = None

class PersonRead(PersonBase):
	model_config = ConfigDict(from_attributes=True)

	military_number: str


class TrainingHoursSummary(BaseModel):
	required_hours: int
	counted_hours: int
	credited_hours: int
	recognized_hours: int
	carryover_hours: int
	unmet_required_hours: int
	remaining_hours: int
	training_status: str
	needs_review_reason: str | None = None
	latest_round: int | None = None
	latest_status: str | None = None
	latest_schedule_id: int | None = None
	over_limit: bool = False
	is_incomplete: bool = False


class PersonRosterRead(PersonRead):
	training_hours_summary: TrainingHoursSummary | None = None
