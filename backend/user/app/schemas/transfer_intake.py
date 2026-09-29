"""Transfer-in intake request and response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from user.app.schemas.person import PersonBase


class TransferPersonDetails(PersonBase):
	military_number: str


class TransferTrainingRecord(BaseModel):
	service_year: int = Field(ge=1, le=6)
	training_year: int = Field(ge=1)
	training_type: str = Field(min_length=1, max_length=50)
	training_round: int = Field(default=1, ge=1, le=3)
	training_hours: int = Field(gt=0)
	notes: str | None = None


class TransferIntakeCreate(BaseModel):
	person: TransferPersonDetails
	training_records: list[TransferTrainingRecord] = Field(default_factory=list)


class TransferIntakeRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	military_number: str
	person_details: TransferPersonDetails
	training_records: list[TransferTrainingRecord]
	status: Literal["pending", "confirmed", "rejected"]
	assigned_squad_id: int | None = None
	submitted_at: datetime
	reviewed_at: datetime | None = None