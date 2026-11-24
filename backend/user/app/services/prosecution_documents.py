"""Persist complaint drafts without changing personnel or training state."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.models.person import Person
from user.app.models.prosecution_document import ProsecutionDocument
from user.app.schemas.prosecution_document import DraftCreate, DraftUpdate
from user.app.services.prosecution_draft import draft_sources


def _encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detail(row: ProsecutionDocument) -> dict:
    snapshot = json.loads(row.training_snapshot_json)
    return {
        'id': row.id, 'person_id': row.person_id, 'fields': json.loads(row.fields_json),
        'training_record_ids': [item['id'] for item in snapshot], 'training_snapshot': snapshot,
        'version': row.version, 'created_at': row.created_at, 'updated_at': row.updated_at,
    }


def _stored(db: Session, identifier: UUID) -> ProsecutionDocument:
    row = db.get(ProsecutionDocument, str(identifier))
    if row is None:
        raise HTTPException(404, '저장된 고발장을 찾을 수 없습니다.')
    return row


def _check_identity(fields: dict[str, str], person_id: str) -> None:
    if fields['military_number'] != person_id:
        raise HTTPException(422, '고발장의 군번과 선택한 대상자가 다릅니다.')


def list_documents(db: Session) -> list[dict]:
    rows = db.scalars(select(ProsecutionDocument).order_by(
        ProsecutionDocument.updated_at.desc(), ProsecutionDocument.id)).all()
    result = []
    for row in rows:
        fields = json.loads(row.fields_json)
        result.append({
            'id': row.id, 'person_id': row.person_id, 'name': fields.get('name', ''),
            'document_number': fields.get('number', ''), 'created_at': row.created_at,
            'updated_at': row.updated_at, 'version': row.version,
        })
    return result


def get_document(db: Session, identifier: UUID) -> dict:
    return _detail(_stored(db, identifier))


def _existing_creation(db: Session, identifier: str, creation_hash: str) -> dict | None:
    existing = db.get(ProsecutionDocument, identifier)
    if existing is None:
        return None
    if existing.creation_hash != creation_hash:
        raise HTTPException(409, '동일한 저장 요청에 다른 내용이 있습니다. 저장된 문서를 다시 불러오세요.')
    return _detail(existing)


def create_document(db: Session, payload: DraftCreate, username: str) -> dict:
    identifier = str(payload.id)
    _check_identity(payload.fields, payload.person_id)
    requested_snapshot = sorted((item.model_dump() for item in payload.training_snapshot), key=lambda item: item['id'])
    creation_hash = hashlib.sha256(_encode({
        'person_id': payload.person_id, 'fields': payload.fields,
        'training_record_ids': payload.training_record_ids,
        'training_snapshot': requested_snapshot,
    }).encode('utf-8')).hexdigest()
    # Retry committed requests before checking eligibility, which may have changed.
    if existing := _existing_creation(db, identifier, creation_hash):
        return existing
    person = db.get(Person, payload.person_id)
    if person is None:
        raise HTTPException(404, '대상자를 찾을 수 없습니다.')
    source = draft_sources(db, person)
    eligible = {item['id']: item for item in source['records']}
    if not source['is_target'] or not set(payload.training_record_ids) <= eligible.keys():
        raise HTTPException(409, '선택한 훈련의 고발 검토 대상 여부가 변경되었습니다. 대상자 정보를 다시 불러오세요.')
    current_snapshot = [eligible[key] for key in payload.training_record_ids]
    if _encode(requested_snapshot) != _encode(current_snapshot):
        raise HTTPException(409, '작성 근거가 변경되었습니다. 초안을 다시 작성하세요.')
    now = _timestamp()
    row = ProsecutionDocument(
        id=identifier, person_id=payload.person_id, fields_json=_encode(payload.fields),
        training_snapshot_json=_encode(current_snapshot),
        creation_hash=creation_hash, version=1, created_at=now, updated_at=now,
        created_by=username[:100], updated_by=username[:100],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if existing := _existing_creation(db, identifier, creation_hash):
            return existing
        raise
    db.refresh(row)
    return _detail(row)


def update_document(db: Session, identifier: UUID, payload: DraftUpdate, username: str) -> dict:
    row = _stored(db, identifier)
    _check_identity(payload.fields, row.person_id)
    # Atomically reject stale edits instead of overwriting another screen.
    result = db.execute(update(ProsecutionDocument).where(
        ProsecutionDocument.id == str(identifier), ProsecutionDocument.version == payload.version,
    ).values(fields_json=_encode(payload.fields), version=payload.version + 1,
             updated_at=_timestamp(), updated_by=username[:100]))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, '다른 화면에서 고발장이 변경되었습니다. 저장된 문서를 다시 불러오세요.')
    db.commit()
    db.refresh(row)
    return _detail(row)
