"""Persisted editable complaint drafts; independent of filing or attendance status."""
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class ProsecutionDocument(Base):
    __tablename__ = 'prosecution_document'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('person.military_number'), index=True)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    training_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    creation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
