"""Person request and response schemas."""

from pydantic import BaseModel, ConfigDict

class PersonBase(BaseModel):
	name: str
	branch: str
	rank: str | None = None
	unit: str | None = None
	specialty: str | None = None
	status: str = "active"
	squad_id: int | None = None

class PersonCreate(PersonBase):
	military_number: str

class PersonUpdate(BaseModel):
	name: str | None = None
	branch: str | None = None
	rank: str | None = None
	unit: str | None = None
	specialty: str | None = None
	status: str | None = None
	squad_id: int | None = None

class PersonRead(PersonBase):
	model_config = ConfigDict(from_attributes=True)

	military_number: str
