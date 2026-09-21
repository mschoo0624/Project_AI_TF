from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PostponementCreate(BaseModel):
    person_id: str
    type: str = "delay"
    reason: str
    training_year: int | None = None
    source_file: str | None = None
    category: str | None = None
    classifier_submission_id: str | None = None


class PostponementRead(PostponementCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    category: str | None = None
    classifier_submission_id: str | None = None
    approved_at: datetime | None = None