"""Copilot conversation history. Each message is also the question log.

A conversation belongs to one browser (`owner` = the browser's random ID) until
the app has a login; then `owner` becomes the user. `response_json` is the full
answer as the screen showed it, so a reopened conversation looks the same.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from user.app.database import Base


class CopilotConversation(Base):
    __tablename__ = "copilot_conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class CopilotMessage(Base):
    __tablename__ = "copilot_message"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("copilot_conversation.id", ondelete="CASCADE"), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    # 질문 검토용: 어떻게 처리됐는지. outcome = answered / asked_back / not_understood / error
    routed_by: Mapped[str] = mapped_column(String(10), nullable=False)
    tool: Mapped[str | None] = mapped_column(String(50), nullable=True)
    args_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    unparsed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    used_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # 제안 카드를 승인했으면 언제, 무엇을 했는지. 다시 열어도 카드가 "✓ 승인함"으로 보인다.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 승인한 변경을 되돌렸으면 언제, 무엇을 했는지. 한 번만 되돌릴 수 있다.
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    undone_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
