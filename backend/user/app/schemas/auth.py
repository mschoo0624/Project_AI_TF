from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BootstrapRequest(BaseModel):
    unit_code: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    unit_code: str = Field(min_length=1, max_length=20)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=256)
    unit_code: str = Field(min_length=1, max_length=20)
    position: Literal["동대장", "상근예비역", "감사실"]
    service_number: str = Field(default="", max_length=20)


class UserUpdate(BaseModel):
    role: Literal["viewer", "scheduler", "approver"] | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class UserRead(BaseModel):
    id: int | None = None
    username: str
    role: str
    is_active: bool = True
    unit_code: str = ""
    position: str = ""
    service_number: str = ""

    @field_validator("unit_code", "position", "service_number", mode="before")
    @classmethod
    def none_to_empty_string(cls, value):
        return "" if value is None else value


class AuthTokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserRead