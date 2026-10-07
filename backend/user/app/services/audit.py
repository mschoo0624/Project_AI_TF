"""Change history for data-changing operations (편성·해제).

Services call record_change() before their own commit, so the log row is saved
in the same transaction as the change. The caller decides where a change came
from with `with change_source("copilot", trace_id):`; the default is the screen.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.audit_log import AuditLog

_source: ContextVar[tuple[str, str | None]] = ContextVar("audit_source", default=("화면", None))


@contextmanager
def change_source(source: str, trace_id: str | None = None) -> Iterator[None]:
	token = _source.set((source, trace_id))
	try:
		yield
	finally:
		_source.reset(token)


def record_change(db: Session, action: str, summary: str, detail: object = None, table_name: str = "person") -> None:
	source, trace_id = _source.get()
	db.add(AuditLog(
		action=action,
		table_name=table_name,
		created_at=datetime.now(timezone.utc).replace(tzinfo=None),
		source=source,
		trace_id=trace_id,
		summary=summary,
		detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
	))


def recent_changes(db: Session, limit: int = 10) -> list[AuditLog]:
	return list(db.scalars(
		select(AuditLog).where(AuditLog.summary.is_not(None))  # 권한 감사 기록(before/after_data)은 빼고 편성 변경만
		.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
	).all())
