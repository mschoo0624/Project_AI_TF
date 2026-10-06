"""AuditLog database model for the SQLite testing phase."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(100), default="미인증 요청", nullable=False)
    before_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
