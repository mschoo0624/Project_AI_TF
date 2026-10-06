"""Training events, daily sessions, and notification delivery state."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TrainingSchedule(Base):
    __tablename__ = "training_schedule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    training_type: Mapped[str] = mapped_column(String(50), nullable=False)
    training_round: Mapped[int] = mapped_column(Integer, nullable=False)
    service_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow_naive, onupdate=_utcnow_naive, nullable=False
    )

    sessions: Mapped[list[TrainingSession]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="TrainingSession.day_number",
    )


class TrainingSession(Base):
    __tablename__ = "training_session"
    __table_args__ = (
        UniqueConstraint("schedule_id", "day_number", name="uq_training_session_day_number"),
        UniqueConstraint("schedule_id", "session_date", name="uq_training_session_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("training_schedule.id", ondelete="CASCADE"), nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    credited_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    schedule: Mapped[TrainingSchedule] = relationship(back_populates="sessions")


class TrainingNotification(Base):
    __tablename__ = "training_notification"

    education_id: Mapped[int] = mapped_column(
        ForeignKey("education.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)


class TrainingResultBatch(Base):
    __tablename__ = "training_result_batch"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)