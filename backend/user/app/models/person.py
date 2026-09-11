"""Person database model for the SQLite testing phase."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base

if TYPE_CHECKING:
    from user.app.models.assignment import Assignment
    from user.app.models.education import Education
    from user.app.models.postponement import Postponement
    from user.app.models.squad import Squad


class Person(Base):
    __tablename__ = "person"

    military_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    branch: Mapped[str] = mapped_column(String(50), default="육군", nullable=False)
    rank: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squad.id"), nullable=True)

    squad: Mapped["Squad | None"] = relationship(back_populates="persons")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="person")
    education_records: Mapped[list["Education"]] = relationship(back_populates="person")
    postponements: Mapped[list["Postponement"]] = relationship(back_populates="person")

