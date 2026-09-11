"""Squad database model for the SQLite testing phase."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base

if TYPE_CHECKING:
    from user.app.models.person import Person


class Squad(Base):
    __tablename__ = "squad"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    persons: Mapped[list["Person"]] = relationship(back_populates="squad")

