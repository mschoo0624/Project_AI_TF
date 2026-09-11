"""Postponement request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PostponementCreate(BaseModel):
	person_id: str
	type: str
	reason: str | None = None


class PostponementRead(PostponementCreate):
	model_config = ConfigDict(from_attributes=True)

	id: int
	status: str
	requested_at: datetime | None = None
	approved_at: datetime | None = None
