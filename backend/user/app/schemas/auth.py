from typing import Literal

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    role: str


class UserUpdate(BaseModel):
    role: Literal["viewer", "scheduler", "approver"] | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class UserRead(BaseModel):
    id: int | None = None
    username: str
    role: str
    is_active: bool = True


class AuthTokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserRead