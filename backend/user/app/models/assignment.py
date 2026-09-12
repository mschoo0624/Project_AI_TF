"""Assignment database model for the SQLite testing phase."""

from __future__ import annotations
from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base

class Assignment(Base):
    __tablename__ = "assignment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squad.id"), nullable=False)
    assigned_date: Mapped[str] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="assigned")

    person: Mapped["Person"] = relationship(back_populates="assignments")
