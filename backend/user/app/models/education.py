"""Education database model for the SQLite testing phase."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base


class Education(Base):
    __tablename__ = "education"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    education_year: Mapped[int] = mapped_column(Integer, nullable=False)
    training_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attendance_status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    training_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped["Person"] = relationship(back_populates="education_records")
