"""Person request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

class PersonBase(BaseModel):
	name: str
	branch: str
	rank: str | None = None
	unit: str | None = None
	specialty: str | None = None
	origin_type: str | None = None
	registration_type: str | None = None
	service_year: int = Field(ge=0, le=8)
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
			"designated",
			"non_designated",
			"student",
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
	service_year: int | None = Field(default=None, ge=0, le=8)
	position: str | None = None
	mobilization_status: str | None = None
	status: str | None = None
	squad_id: int | None = None

class PersonRead(PersonBase):
	model_config = ConfigDict(from_attributes=True)

	military_number: str
