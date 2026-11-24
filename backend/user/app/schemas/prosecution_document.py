import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


FIELDS = {
    'number', 'date', 'police', 'commander', 'complainant_address', 'office_phone',
    'mobile_phone', 'name', 'birth_digits', 'address', 'phone', 'home_phone',
    'work_phone', 'reserve_unit', 'rank', 'military_number', 'offense', 'law',
    'period', 'location', 'delivered_at', 'deliverer', 'recipient',
    'summary', 'reason', 'evidence', 'repeat',
}
FIELD_LIMITS = {
    'summary': 6000, 'reason': 6000, 'evidence': 6000,
    'period': 1500, 'reserve_unit': 1500,
}


class DraftFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: dict[str, StrictStr]

    @field_validator('fields')
    @classmethod
    def validate_fields(cls, value: dict[str, str]) -> dict[str, str]:
        if not value.keys() <= FIELDS:
            raise ValueError('알 수 없는 고발장 항목입니다.')
        for key, text in value.items():
            limit = FIELD_LIMITS.get(key, 200)
            if len(text) > limit:
                raise ValueError(f'{key}: 최대 {limit}자까지 입력할 수 있습니다.')
        if value.get('birth_digits') and not re.fullmatch(r'[0-9]{6}', value['birth_digits']):
            raise ValueError('주민번호 앞자리는 숫자 6자리로 입력하세요.')
        if value.get('repeat', '') not in {'', 'first', 'repeat'}:
            raise ValueError('초범·재범 선택값이 올바르지 않습니다.')
        return {key: value.get(key, '') for key in sorted(FIELDS)}


class TrainingSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: int = Field(gt=0)
    training_type: str = Field(max_length=200)
    training_round: int
    service_year: int
    dates: list[str] = Field(max_length=1000)
    attendance_status: str = Field(max_length=50)
    confirmed_by: str = Field(max_length=100)
    schedule_title: str = Field(default='', max_length=160)
    training_year: int | None = None
    scheduled_hours: int | None = None
    completed_hours: int = 0
    confirmed_at: str | None = None


class DraftCreate(DraftFields):
    id: UUID
    person_id: str = Field(min_length=1, max_length=50)
    training_record_ids: list[StrictInt] = Field(min_length=1, max_length=100)
    training_snapshot: list[TrainingSnapshot] = Field(min_length=1, max_length=100)

    @field_validator('training_record_ids')
    @classmethod
    def validate_record_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(item <= 0 for item in value):
            raise ValueError('훈련 기록을 중복 없이 선택하세요.')
        return sorted(value)


class DraftUpdate(DraftFields):
    version: StrictInt = Field(ge=1)
