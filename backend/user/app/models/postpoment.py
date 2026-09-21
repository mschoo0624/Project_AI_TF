from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class Postponement(Base):
    __tablename__ = "postponement"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="delay", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    training_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classifier_submission_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)