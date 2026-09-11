"""AuditLog database model for the SQLite testing phase."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
