"""Pending transfer-in submissions awaiting personnel review."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class TransferIntake(Base):
    __tablename__ = "transfer_intake"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    military_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    person_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    training_records: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)