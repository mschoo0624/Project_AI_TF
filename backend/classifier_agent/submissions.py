"""Durable submission storage for the Qwen service, independent of legacy data."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3


def root():
    path = Path(os.getenv('CLASSIFIER_DATA_DIR', str(Path(__file__).parent/'data')))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect():
    db = sqlite3.connect(root()/'submissions.sqlite3', timeout=15)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            yield db
    finally:
        db.close()


def save(item):
    with connect() as db:
        db.execute('INSERT INTO submissions VALUES (?, ?)', (item['id'], json.dumps(item, ensure_ascii=False)))
    return item


def list_all():
    with connect() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM submissions ORDER BY rowid DESC')]


def get(id):
    with connect() as db:
        row = db.execute('SELECT payload FROM submissions WHERE id=?', (id,)).fetchone()
    if row is None: raise KeyError(id)
    return json.loads(row[0])


def update(id, mutate):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT payload FROM submissions WHERE id=?', (id,)).fetchone()
        if row is None: raise KeyError(id)
        item = json.loads(row[0])
        mutate(item)
        db.execute('UPDATE submissions SET payload=? WHERE id=?', (json.dumps(item, ensure_ascii=False), id))
    return item


def now(): return datetime.now(timezone.utc).isoformat()
