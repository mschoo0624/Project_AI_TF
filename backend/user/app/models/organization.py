"""Editable unit hierarchy; squad membership remains in the existing squad/person tables."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class OrganizationNode(Base):
    __tablename__ = "organization_node"
    __table_args__ = (UniqueConstraint("squad_id", name="uq_organization_squad"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organization_node.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squad.id"), nullable=True)
    # Confirmed capacity: 11 per squad; parent totals are computed from descendants.
    planned_strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
