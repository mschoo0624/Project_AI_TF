"""Complaint persistence uses synthetic records in a temporary SQLite database."""
from datetime import date, datetime
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from user.app import models
from user.app.api.prosecution_documents import router
from user.app.database import get_db
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.prosecution_document import ProsecutionDocument
from user.app.models.training_schedule import TrainingSchedule, TrainingSession
from user.app.services.prosecution_draft import draft_sources


@pytest.fixture
def environment(tmp_path):
    path = tmp_path / 'complaints.sqlite3'
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    models.Person.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Person(military_number='test-001', name='가상대상자', branch='육군', rank='병장',
                   service_year=3, mobilization_status='동원미지정'),
            Person(military_number='test-002', name='다른사람', branch='육군', rank='병장',
                   service_year=3, mobilization_status='동원미지정'),
        ])
        db.flush()
        for owner in ('test-001', 'test-002'):
            db.add_all([Education(person_id=owner, education_year=3, training_year=2020,
                                  scheduled_date=date(2020, month, 1), training_type='동원훈련Ⅱ형',
                                  training_round=month, attendance_status='무단불참', confirmed_by='test-reviewer')
                        for month in (1, 2, 3)])
        db.commit()
        ids = list(db.scalars(select(Education.id).where(Education.person_id == 'test-001')).all())
        other_id = db.scalar(select(Education.id).where(Education.person_id == 'test-002'))
        snapshot = draft_sources(db, db.get(Person, 'test-001'))['records']
    app = FastAPI()
    app.include_router(router)
    def dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    payload = {
        'id': str(uuid4()), 'person_id': 'test-001', 'training_record_ids': ids,
        'training_snapshot': snapshot,
        'fields': {'name': '가상대상자', 'military_number': 'test-001', 'number': '가상-001',
                   'summary': '자동 입력한 내용과 담당자 작성 내용', 'reason': '', 'birth_digits': ''},
    }
    with TestClient(app) as client:
        yield client, engine, path, payload, other_id
    engine.dispose()


def test_create_list_reload_and_reopen_database(environment):
    client, engine, path, payload, _ = environment
    response = client.post('/prosecution-documents', json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['version'] == 1
    assert saved['created_at'].endswith('+00:00')
    assert saved['training_snapshot'][0]['dates'] == ['2020-01-01']
    assert saved['training_record_ids'] == payload['training_record_ids']
    assert client.get('/prosecution-documents/' + saved['id']).json() == saved
    listed = client.get('/prosecution-documents').json()
    assert len(listed) == 1 and listed[0]['name'] == '가상대상자'
    assert listed[0]['document_number'] == '가상-001'
    # A new engine/session proves persistence outside the request and its connection.
    reopened = create_engine(f'sqlite:///{path}')
    with Session(reopened) as db:
        row = db.get(ProsecutionDocument, saved['id'])
        assert row is not None and '담당자 작성 내용' in row.fields_json
        assert db.get(Person, 'test-001').name == '가상대상자'
        assert set(db.scalars(select(Education.attendance_status))) == {'무단불참'}
    reopened.dispose()


def test_linked_training_details_are_saved_and_changes_require_refresh(environment):
    client, engine, _, payload, _ = environment
    with Session(engine) as db:
        schedule = TrainingSchedule(title='가상 연동 훈련', training_type='동원훈련Ⅱ형',
                                    training_round=1, service_year=3)
        schedule.sessions = [TrainingSession(day_number=1, session_date=date(2020, 1, 1), credited_hours=8)]
        db.add(schedule)
        record = db.get(Education, payload['training_record_ids'][0])
        record.schedule = schedule
        record.confirmed_at = datetime(2020, 1, 2, 3, 4)
        db.commit()
        payload['training_snapshot'] = draft_sources(db, db.get(Person, 'test-001'))['records']
        schedule_id = schedule.id
    saved = client.post('/prosecution-documents', json=payload)
    assert saved.status_code == 201, saved.text
    snapshot = saved.json()['training_snapshot'][0]
    assert snapshot['schedule_title'] == '가상 연동 훈련'
    assert snapshot['scheduled_hours'] == 8 and snapshot['completed_hours'] == 0
    assert snapshot['training_year'] == 2020
    assert snapshot['confirmed_at'] == '2020-01-02T03:04:00+00:00'
    with Session(engine) as db:
        schedule = db.get(TrainingSchedule, schedule_id)
        schedule.title = '수정된 연동 훈련'
        schedule.sessions[0].credited_hours = 4
        db.commit()
    stale = {**payload, 'id': str(uuid4())}
    rejected = client.post('/prosecution-documents', json=stale)
    assert rejected.status_code == 409
    # Saved documents keep their original facts even when linked data later changes.
    reopened = client.get('/prosecution-documents/' + saved.json()['id']).json()
    assert reopened['training_snapshot'][0] == snapshot


def test_full_unit_path_allows_1500_characters_and_rejects_longer(environment):
    client, _, _, payload, _ = environment
    payload['fields']['reserve_unit'] = '부대' * 750
    response = client.post('/prosecution-documents', json=payload)
    assert response.status_code == 201, response.text
    assert response.json()['fields']['reserve_unit'] == payload['fields']['reserve_unit']
    payload['fields']['reserve_unit'] += '명'
    rejected = client.put('/prosecution-documents/' + response.json()['id'], json={
        'version': 1, 'fields': payload['fields'],
    })
    assert rejected.status_code == 422


def test_older_saved_snapshots_remain_readable_and_editable(environment):
    client, engine, _, payload, _ = environment
    saved = client.post('/prosecution-documents', json=payload).json()
    old_keys = {'id', 'training_type', 'training_round', 'service_year', 'dates',
                'attendance_status', 'confirmed_by'}
    old_snapshot = [{key: value for key, value in item.items() if key in old_keys}
                    for item in saved['training_snapshot']]
    with Session(engine) as db:
        row = db.get(ProsecutionDocument, saved['id'])
        row.training_snapshot_json = json.dumps(old_snapshot, ensure_ascii=False)
        db.commit()
    reopened = client.get('/prosecution-documents/' + saved['id'])
    assert reopened.status_code == 200
    assert reopened.json()['training_snapshot'] == old_snapshot
    edited = client.put('/prosecution-documents/' + saved['id'], json={
        'version': 1, 'fields': {**saved['fields'], 'reason': '이전 문서 수정'},
    })
    assert edited.status_code == 200
    assert edited.json()['training_snapshot'] == old_snapshot


def test_duplicate_create_is_idempotent_but_changed_payload_conflicts(environment):
    client, engine, _, payload, _ = environment
    first = client.post('/prosecution-documents', json=payload)
    second = client.post('/prosecution-documents', json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    changed = {**payload, 'fields': {**payload['fields'], 'summary': '다른 내용'}}
    assert client.post('/prosecution-documents', json=changed).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProsecutionDocument)) == 1


def test_changed_source_rejects_first_save_but_not_completed_request_retry(environment):
    client, engine, _, payload, _ = environment
    with Session(engine) as db:
        record = db.get(Education, payload['training_record_ids'][0])
        record.scheduled_date = date(2020, 1, 5)
        record.confirmed_by = 'different-reviewer'
        db.commit()
    rejected = client.post('/prosecution-documents', json=payload)
    assert rejected.status_code == 409
    assert '작성 근거가 변경' in rejected.json()['detail']
    assert client.get('/prosecution-documents').json() == []
    with Session(engine) as db:
        payload['training_snapshot'] = draft_sources(db, db.get(Person, 'test-001'))['records']
    saved = client.post('/prosecution-documents', json=payload)
    assert saved.status_code == 201
    with Session(engine) as db:
        for record in db.scalars(select(Education)):
            record.attendance_status = 'completed'
        db.commit()
    retried = client.post('/prosecution-documents', json=payload)
    assert retried.status_code == 201
    assert retried.json() == saved.json()


def test_update_rejects_stale_version_and_preserves_original_training(environment):
    client, engine, _, payload, _ = environment
    saved = client.post('/prosecution-documents', json=payload).json()
    # Historical saved documents remain available after attendance/eligibility changes.
    with Session(engine) as db:
        for record in db.scalars(select(Education)):
            record.attendance_status = 'completed'
        db.commit()
    updated_fields = {**saved['fields'], 'reason': '담당자 수정내용'}
    update_payload = {'version': saved['version'], 'fields': updated_fields}
    response = client.put('/prosecution-documents/' + saved['id'], json=update_payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['version'] == 2
    assert updated['fields']['reason'] == '담당자 수정내용'
    assert updated['training_snapshot'] == saved['training_snapshot']
    assert updated['created_at'] == saved['created_at']
    assert client.put('/prosecution-documents/' + saved['id'], json=update_payload).status_code == 409
    assert client.get('/prosecution-documents/' + saved['id']).json()['fields']['reason'] == '담당자 수정내용'


def test_create_rejects_another_person_training(environment):
    client, _, _, payload, other_id = environment
    payload['training_record_ids'] = [other_id]
    assert client.post('/prosecution-documents', json=payload).status_code == 409
    assert client.get('/prosecution-documents').json() == []


@pytest.mark.parametrize('field,value', [
    ('birth_digits', '010101-1234567'), ('unexpected', 'value'),
    ('summary', 'x' * 6001), ('repeat', 'unknown'), ('name', 123),
])
def test_rejects_invalid_field_values(environment, field, value):
    client, _, _, payload, _ = environment
    payload['fields'][field] = value
    assert client.post('/prosecution-documents', json=payload).status_code == 422


def test_identity_immutable_and_missing_document_is_404(environment):
    client, _, _, payload, _ = environment
    saved = client.post('/prosecution-documents', json=payload).json()
    fields = {**saved['fields'], 'military_number': 'test-002'}
    assert client.put('/prosecution-documents/' + saved['id'], json={'fields': fields, 'version': 1}).status_code == 422
    assert client.get('/prosecution-documents/' + str(uuid4())).status_code == 404
    assert client.get('/prosecution-documents/not-a-uuid').status_code == 422
