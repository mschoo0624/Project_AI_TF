"""Persistent failed-login counters shared by API workers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class AuthLoginFailure(Base):
    __tablename__ = "auth_login_failure"
    __table_args__ = (Index("ix_auth_login_failure_key_time", "key_hash", "failed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    failed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)