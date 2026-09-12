"""Training record request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class TrainingRecordCreate(BaseModel):
	service_year: int = Field(ge=1, le=6, description="Original obligation year")
	training_type: str = Field(default="기본훈련")
	training_hours: int = Field(ge=0)
	training_round: int = Field(default=1, ge=1, le=3)
	attendance_status: str = Field(default="completed")
	notes: str | None = None


class TrainingRecordRead(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	person_id: str
	education_year: int
	training_year: int | None = None
	training_type: str
	training_round: int
	attendance_status: str
	training_hours: int
	notes: str | None = None