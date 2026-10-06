from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class TrainingSessionCreate(BaseModel):
    day_number: int = Field(ge=1, le=30)
    session_date: date
    credited_hours: int = Field(ge=0, le=24)


class TrainingSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_number: int
    session_date: date
    credited_hours: int


class TrainingScheduleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    training_type: str = Field(min_length=1, max_length=50)
    training_round: int = Field(ge=1, le=3)
    service_year: int = Field(ge=1, le=99)
    sessions: list[TrainingSessionCreate] = Field(min_length=1, max_length=30)


class TrainingScheduleMove(BaseModel):
    expected_version: int = Field(ge=1)
    sessions: list[TrainingSessionCreate] = Field(min_length=1, max_length=30)


class TrainingScheduleUpdate(TrainingScheduleCreate):
    expected_version: int = Field(ge=1)


class TrainingScheduleVersion(BaseModel):
    expected_version: int = Field(ge=1)


class TrainingScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    training_type: str
    training_round: int
    service_year: int
    status: str
    demo_early_save_enabled: bool
    demo_early_save_used: bool
    version: int
    sessions: list[TrainingSessionRead]


class TrainingRosterAssignment(BaseModel):
    person_ids: list[str] = Field(min_length=1, max_length=500)


class TrainingResultEntry(BaseModel):
    education_id: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    attendance_status: str
    training_hours: int = Field(ge=0, le=24 * 30)
    notes: str | None = Field(default=None, max_length=2000)
    reversal_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    override_allowance: bool = False
    override_reason: str | None = Field(default=None, max_length=1000)


class TrainingResultBatchConfirm(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    source_kind: str = Field(default="manual")
    entries: list[TrainingResultEntry] = Field(min_length=1, max_length=500)