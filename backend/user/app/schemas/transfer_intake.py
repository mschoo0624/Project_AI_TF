"""Transfer-in intake request and response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from user.app.schemas.person import PersonBase


class TransferPersonDetails(PersonBase):
	military_number: str


class TransferTrainingRecord(BaseModel):
	service_year: int = Field(ge=1, le=99)
	training_year: int = Field(ge=1)
	training_type: str = Field(min_length=1, max_length=50)
	training_round: int = Field(default=1, ge=1, le=3)
	training_hours: int = Field(ge=0)
	attendance_status: str = "completed"
	confirmed_by: str | None = None
	notes: str | None = None

	@model_validator(mode="after")
	def validate_attendance_evidence(self):
		counted = {"이수", "completed", "참석", "attended"}
		no_show = {"무단불참", "무단_불참", "unexcused_absence"}
		valid = counted | no_show | {"연기", "postponed", "보류", "round_hold", "scheduled", "훈련 예정"}
		if self.attendance_status not in valid:
			raise ValueError("Unknown transfer attendance status")
		if self.attendance_status in no_show and not (self.confirmed_by and self.confirmed_by.strip()):
			raise ValueError("A confirmed transfer no-show requires confirmed_by")
		if self.attendance_status in counted and self.training_hours < 1:
			raise ValueError("Completed transfer training requires positive hours")
		if self.attendance_status not in counted and self.training_hours != 0:
			raise ValueError("Non-attendance transfer records must have zero hours")
		return self


class TransferCarryover(BaseModel):
	origin_year: int = Field(ge=1, le=99)
	training_type: str = Field(min_length=1, max_length=50)
	origin_round: int = Field(default=1, ge=1, le=3)
	current_round: int = Field(default=1, ge=1, le=3)
	hours: int = Field(gt=0)


class TransferIntakeCreate(BaseModel):
	person: TransferPersonDetails
	training_records: list[TransferTrainingRecord] = Field(default_factory=list)
	carryovers: list[TransferCarryover] = Field(default_factory=list)


class TransferIntakeRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	military_number: str
	person_details: TransferPersonDetails
	training_records: list[TransferTrainingRecord]
	carryovers: list[TransferCarryover] = Field(default_factory=list)
	status: Literal["pending", "confirmed", "rejected"]
	assigned_squad_id: int | None = None
	submitted_at: datetime
	reviewed_at: datetime | None = None