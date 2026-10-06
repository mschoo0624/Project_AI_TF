from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PostponementCreate(BaseModel):
    person_id: str
    type: str = "delay"
    reason: str
    training_year: int | None = None
    education_record_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    credited_hours: int | None = Field(default=None, ge=0)
    source_file: str | None = None
    category: str | None = None
    classifier_submission_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class PostponementUpdate(BaseModel):
    type: str | None = None
    reason: str | None = None
    training_year: int | None = None
    education_record_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    credited_hours: int | None = Field(default=None, ge=0)
    category: str | None = None


class PostponementRead(PostponementCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    category: str | None = None
    classifier_submission_id: str | None = None
    approved_at: datetime | None = None
    resolution_reported_at: datetime | None = None
    decided_by: str | None = None