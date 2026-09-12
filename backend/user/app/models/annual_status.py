"""Annual mobilization status for a reservist."""
# 인원별, 연도별 동원 상태 테이블입니다.

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user.app.database import Base


class AnnualStatus(Base):
    __tablename__ = "annual_status"

    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.military_number"), primary_key=True
    )
    service_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    mobilization_status: Mapped[str] = mapped_column(String(20), nullable=False)

    person: Mapped["Person"] = relationship(back_populates="annual_statuses")