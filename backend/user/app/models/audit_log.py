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
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 언제, 어디서(화면/copilot), 무엇을 바꿨는지. detail은 JSON 문자열(대상 인원·분대 목록).
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
