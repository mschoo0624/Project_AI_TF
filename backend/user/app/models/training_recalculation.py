"""Persisted outputs and policy inputs for reserve-training recalculation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TrainingStatusPolicy(Base):
    __tablename__ = "training_status_policy"

    status_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    counts_hours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credits_hours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    advances_round: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_absence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prosecution_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)


class TrainingCarryover(Base):
    __tablename__ = "training_carryover"
    __table_args__ = (
        UniqueConstraint(
            "person_id", "origin_year", "training_type", "origin_round",
            name="uq_training_carryover_origin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    origin_year: Mapped[int] = mapped_column(Integer, nullable=False)
    training_type: Mapped[str] = mapped_column(String(50), nullable=False)
    origin_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    original_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remaining_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    converted_from_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)


class TrainingCarryoverResolution(Base):
    __tablename__ = "training_carryover_resolution"
    __table_args__ = (
        UniqueConstraint("carryover_id", "education_id", name="uq_carryover_resolution_record"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    carryover_id: Mapped[int] = mapped_column(
        ForeignKey("training_carryover.id", ondelete="CASCADE"), nullable=False
    )
    education_id: Mapped[int] = mapped_column(ForeignKey("education.id"), nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)


class TrainingYearResult(Base):
    __tablename__ = "training_year_result"
    __table_args__ = (
        UniqueConstraint("person_id", "service_year", "training_type", name="uq_training_year_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    service_year: Mapped[int] = mapped_column(Integer, nullable=False)
    training_type: Mapped[str] = mapped_column(String(50), nullable=False)
    required_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    counted_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credited_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmet_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    carryover_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    needs_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recalculated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)


class TrainingRoundState(Base):
    __tablename__ = "training_round_state"
    __table_args__ = (
        UniqueConstraint("person_id", "training_type", name="uq_training_round_person_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.military_number"), nullable=False)
    training_type: Mapped[str] = mapped_column(String(50), nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recalculated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)


class TrainingRolloverRun(Base):
    __tablename__ = "training_rollover_run"

    calendar_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)