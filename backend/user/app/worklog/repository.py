from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3


KST = timezone(timedelta(hours=9))
DEFAULT_PATH = Path(__file__).resolve().parents[3] / 'worklogs.sqlite3'


class ChangedWorkLog(Exception):
    pass


def now() -> datetime:
    return datetime.now(KST)


def today() -> str:
    return now().date().isoformat()


def _timestamp(value: datetime | str | None = None) -> str:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value or now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).isoformat()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


@contextmanager
def _connection():
    path = Path(os.environ.get('WORKLOG_DB_PATH', str(DEFAULT_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS worklog_day (
                date TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS worklog_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL REFERENCES worklog_day(date),
                occurred_at TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                summary TEXT NOT NULL,
                actor TEXT NOT NULL,
                people_json TEXT NOT NULL,
                details_json TEXT NOT NULL,
                dedupe_key TEXT UNIQUE
            );
            CREATE INDEX IF NOT EXISTS worklog_event_date ON worklog_event(date, id);
            CREATE TABLE IF NOT EXISTS worklog_revision (
                date TEXT NOT NULL REFERENCES worklog_day(date),
                revision INTEGER NOT NULL,
                confirmed_at TEXT NOT NULL,
                confirmed_by TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                last_event_id INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                pdf BLOB NOT NULL,
                PRIMARY KEY(date, revision)
            );
        ''')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_day(db: sqlite3.Connection, day: str) -> None:
    date.fromisoformat(day)
    db.execute('INSERT OR IGNORE INTO worklog_day(date, created_at) VALUES (?, ?)', (day, _timestamp()))


def initialize() -> None:
    with _connection() as db:
        _ensure_day(db, today())


def _event(row: sqlite3.Row) -> dict:
    result = dict(row)
    result['people'] = json.loads(result.pop('people_json'))
    result['details'] = json.loads(result.pop('details_json'))
    result.pop('dedupe_key')
    return result


def append_event(*, category: str, action: str, summary: str, actor: str,
                 people: list[dict], details: dict, occurred_at: datetime | str | None = None,
                 dedupe_key: str | None = None) -> dict:
    stamp = _timestamp(occurred_at)
    day = stamp[:10]
    with _connection() as db:
        db.execute('BEGIN IMMEDIATE')
        _ensure_day(db, day)
        if dedupe_key:
            previous = db.execute('SELECT * FROM worklog_event WHERE dedupe_key = ?', (dedupe_key,)).fetchone()
            if previous:
                return _event(previous)
        cursor = db.execute('''
            INSERT INTO worklog_event
                (date, occurred_at, category, action, summary, actor, people_json, details_json, dedupe_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (day, stamp, category, action, summary, actor, _json(people), _json(details), dedupe_key))
        return _event(db.execute('SELECT * FROM worklog_event WHERE id = ?', (cursor.lastrowid,)).fetchone())


def _detail(db: sqlite3.Connection, day: str) -> dict | None:
    row = db.execute('SELECT * FROM worklog_day WHERE date = ?', (day,)).fetchone()
    if row is None:
        return None
    events = [_event(item) for item in db.execute('SELECT * FROM worklog_event WHERE date = ? ORDER BY id', (day,))]
    revisions = [dict(item) for item in db.execute('''
        SELECT revision, confirmed_at, confirmed_by, event_count, last_event_id
        FROM worklog_revision WHERE date = ? ORDER BY revision DESC
    ''', (day,))]
    last_id = events[-1]['id'] if events else 0
    return {'date': day, 'events': events, 'notes': row['notes'], 'revisions': revisions,
            'last_event_id': last_id,
            'has_unconfirmed_changes': not revisions or revisions[0]['last_event_id'] != last_id}


def ensure_today() -> dict:
    day = today()
    with _connection() as db:
        _ensure_day(db, day)
        return _detail(db, day)


def get_day(day: str) -> dict | None:
    with _connection() as db:
        return _detail(db, day)


def list_days() -> list[dict]:
    with _connection() as db:
        _ensure_day(db, today())
        rows = db.execute('''
            SELECT d.date, COUNT(e.id) AS event_count, COALESCE(MAX(e.id), 0) AS last_event_id,
                COALESCE((SELECT MAX(r.revision) FROM worklog_revision r WHERE r.date=d.date), 0) AS revision,
                (SELECT r.confirmed_at FROM worklog_revision r WHERE r.date=d.date ORDER BY r.revision DESC LIMIT 1) AS confirmed_at,
                (SELECT r.last_event_id FROM worklog_revision r WHERE r.date=d.date ORDER BY r.revision DESC LIMIT 1) AS confirmed_event_id
            FROM worklog_day d LEFT JOIN worklog_event e ON e.date=d.date
            GROUP BY d.date ORDER BY d.date DESC
        ''')
        return [{**dict(row), 'has_unconfirmed_changes': row['confirmed_event_id'] != row['last_event_id']} for row in rows]


def preview(day: str, *, notes: str, expected_event_id: int) -> bytes:
    from .pdf import render_pdf

    detail = get_day(day)
    if detail is None:
        raise KeyError(day)
    if detail['last_event_id'] != expected_event_id:
        raise ChangedWorkLog('새 업무가 추가되었습니다. 목록을 새로고침한 뒤 다시 미리보기 하세요.')
    snapshot = {'date': day, 'events': detail['events'], 'notes': notes}
    return render_pdf(snapshot, revision=0, confirmed_by='', preview=True)


def confirm(day: str, *, notes: str, expected_event_id: int, actor: str) -> dict:
    from .pdf import render_pdf

    with _connection() as db:
        db.execute('BEGIN IMMEDIATE')
        detail = _detail(db, day)
        if detail is None:
            raise KeyError(day)
        if detail['last_event_id'] != expected_event_id:
            raise ChangedWorkLog('새 업무가 추가되었습니다. 목록을 새로고침한 뒤 다시 확인하세요.')
        snapshot = {'date': day, 'events': detail['events'], 'notes': notes}
        encoded = _json(snapshot)
        latest = db.execute('SELECT * FROM worklog_revision WHERE date = ? ORDER BY revision DESC LIMIT 1', (day,)).fetchone()
        if latest is not None and latest['snapshot_json'] == encoded:
            return _detail(db, day)
        revision = latest['revision'] + 1 if latest else 1
        confirmed_at = _timestamp()
        pdf = render_pdf(snapshot, revision=revision, confirmed_by=actor)
        db.execute('''INSERT INTO worklog_revision
            (date, revision, confirmed_at, confirmed_by, event_count, last_event_id, snapshot_json, pdf)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (day, revision, confirmed_at, actor, len(detail['events']), expected_event_id, encoded, pdf))
        db.execute('UPDATE worklog_day SET notes = ? WHERE date = ?', (notes, day))
        return _detail(db, day)


def get_pdf(day: str, revision: int) -> bytes | None:
    with _connection() as db:
        row = db.execute('SELECT pdf FROM worklog_revision WHERE date = ? AND revision = ?', (day, revision)).fetchone()
        return bytes(row['pdf']) if row else None
