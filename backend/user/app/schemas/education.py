"""Training record request and response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TrainingRecordCreate(BaseModel):
	service_year: int = Field(ge=1, le=99, description="Original obligation year")
	training_year: int | None = Field(default=None, ge=1)
	scheduled_date: date | None = None
	training_type: str = Field(default="기본훈련")
	training_hours: int = Field(ge=0)
	training_round: int = Field(default=1, ge=1, le=3)
	attendance_status: str = Field(default="completed")
	confirmed_by: str | None = None
	notes: str | None = None


class TrainingRecordUpdate(BaseModel):
	expected_version: int | None = Field(default=None, ge=1)
	service_year: int | None = Field(default=None, ge=1, le=99)
	training_year: int | None = Field(default=None, ge=1)
	scheduled_date: date | None = None
	training_hours: int | None = Field(default=None, ge=0)
	training_type: str | None = None
	training_round: int | None = Field(default=None, ge=1, le=3)
	attendance_status: str | None = None
	confirmed_by: str | None = None
	notes: str | None = None
	reversal_reason: str | None = Field(default=None, min_length=1, max_length=1000)


class TrainingRecordRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	person_id: str
	education_year: int
	training_year: int | None = None
	scheduled_date: date | None = None
	training_type: str
	training_round: int
	attendance_status: str
	training_hours: int
	source_kind: str = "attendance"
	confirmed_by: str | None = None
	confirmed_at: datetime | None = None
	version: int
	notes: str | None = None