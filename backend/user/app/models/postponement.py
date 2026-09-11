"""Postponement database model for the SQLite testing phase."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base


class Postponement(Base):
    __tablename__ = "postponement"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    person: Mapped["Person"] = relationship(back_populates="postponements")
