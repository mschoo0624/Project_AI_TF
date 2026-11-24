"""Daily-log capture tests use synthetic requests and isolated SQLite databases."""
from datetime import date
import json
import re
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from user.app import models
from user.app.database import get_db
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.education import Education
from user.app.models.squad import Squad
from user.app.worklog.events import match_operation
from user.app.worklog.middleware import WorkLogMiddleware


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSIFIER_DATA_DIR', str(tmp_path / 'submissions'))
    engine = create_engine(f'sqlite:///{tmp_path / "business.sqlite3"}', connect_args={'check_same_thread': False})
    models.Person.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Squad(id=1, name='가상분대'))
        db.flush()
        db.add_all([Person(military_number=f'test-{index:03}', name=f'가상인원{index}', branch='육군',
                           rank='병장', position='소총수', unit='가상부대', service_year=3, squad_id=1,
                           mobilization_status='동원미지정') for index in (1, 2)])
        db.commit()
    app, captured = FastAPI(), []
    app.add_middleware(WorkLogMiddleware, session_factory=factory, writer=lambda **event: captured.append(event))
    def dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    yield app, captured, factory
    engine.dispose()


def test_success_failure_noop_and_deleted_identity(environment):
    app, captured, factory = environment
    @app.patch('/persons/{number}')
    def edit(number: str, values: dict):
        if values.get('reject'):
            raise HTTPException(422, 'invalid')
        with factory() as db:
            row = db.get(Person, number)
            row.name = values['name']
            db.commit()
            return {'military_number': number, 'name': row.name}
    @app.delete('/persons/{number}', status_code=204)
    def remove(number: str):
        with factory() as db:
            db.delete(db.get(Person, number))
            db.commit()
    with TestClient(app) as client:
        assert client.patch('/persons/test-001', json={'name': '변경이름', 'password': 'secret', 'rrn': 'private'}).status_code == 200
        assert client.patch('/persons/test-001', json={'name': '변경이름'}).status_code == 200
        assert client.patch('/persons/test-001', json={'reject': True}).status_code == 422
        assert len(captured) == 1
        assert captured[0]['people'][0]['name'] == '변경이름'
        assert captured[0]['people'][0]['position'] == '소총수'
        encoded = json.dumps(captured, ensure_ascii=False)
        assert 'secret' not in encoded and 'private' not in encoded
        assert client.delete('/persons/test-001').status_code == 204
        assert len(captured) == 2
        assert captured[1]['people'][0]['name'] == '변경이름'
        assert captured[1]['action'] == 'personnel.delete'


def test_full_assignment_release_records_every_person_and_excludes_noop(environment):
    app, captured, factory = environment
    @app.post('/squads/assignments/reset')
    def release():
        with factory() as db:
            rows = db.scalars(select(Person).where(Person.squad_id.is_not(None))).all()
            for row in rows:
                row.squad_id = None
            db.commit()
            return {'reset_count': len(rows)}
    with TestClient(app) as client:
        assert client.post('/squads/assignments/reset').status_code == 200
        assert client.post('/squads/assignments/reset').status_code == 200
    assert len(captured) == 1
    assert {person['military_number'] for person in captured[0]['people']} == {'test-001', 'test-002'}
    assert all(person['squad_id'] is None for person in captured[0]['people'])
    assert len(captured[0]['details']['변경 항목']) == 2


def test_real_prosecution_router_retries_do_not_duplicate_entry(environment):
    from user.app.api.prosecution_documents import router
    from user.app.services.prosecution_draft import draft_sources
    app, captured, factory = environment
    app.include_router(router)
    with factory() as db:
        db.add_all([Education(person_id='test-001', education_year=3, training_year=2020,
                              scheduled_date=date(2020, month, 1), training_type='동원훈련Ⅱ형',
                              training_round=month, attendance_status='무단불참', confirmed_by='test') for month in (1, 2, 3)])
        db.commit()
        sources = draft_sources(db, db.get(Person, 'test-001'))
    payload = {'id': str(uuid4()), 'person_id': 'test-001',
               'training_record_ids': [row['id'] for row in sources['records']], 'training_snapshot': sources['records'],
               'fields': {'military_number': 'test-001', 'name': '가상인원1', 'number': '가상-001', 'birth_digits': '010203'}}
    with TestClient(app) as client:
        assert client.post('/prosecution-documents', json=payload).status_code == 201
        assert client.post('/prosecution-documents', json=payload).status_code == 201
        assert len(captured) == 1
        assert captured[0]['category'] == 'prosecution'
        assert '010203' not in json.dumps(captured)
        assert client.put('/prosecution-documents/' + payload['id'], json={'version': 1, 'fields': payload['fields']}).status_code == 200
        assert len(captured) == 2
        assert captured[0]['dedupe_key'] != captured[1]['dedupe_key']


def test_new_training_record_does_not_report_old_records_as_deleted(environment):
    app, captured, factory = environment
    with factory() as db:
        db.add(Education(person_id='test-001', education_year=3, training_hours=1))
        db.commit()
    @app.post('/reservists/{number}/training-hours')
    def add(number: str):
        with factory() as db:
            row = Education(person_id=number, education_year=3, training_hours=2)
            db.add(row)
            db.commit()
            return {'id': row.id, 'person_id': number}
    with TestClient(app) as client:
        assert client.post('/reservists/test-001/training-hours').status_code == 200
    assert len(captured) == 1
    changes = captured[0]['details']['변경 항목']
    assert all(change['대상'] == '훈련 기록 2' for change in changes)
    assert all(change['이전'] is None for change in changes)


def test_classifier_upload_body_not_retained_and_linked_decision_not_duplicated(environment):
    from classifier_agent import submissions
    app, captured, factory = environment
    @app.post('/classifier-api/submissions', status_code=202)
    def upload(file: UploadFile = File(...)):
        assert file.file.read() == b'%PDF private document bytes'
        return submissions.save({'id': 'synthetic', 'filename': file.filename, 'military_number': 'test-001',
                                 'applicant_name': '가상인원1', 'reason_category': '질병', 'application_type': 'postponement.illness', 'status': 'pending',
                                 'analysis_state': 'completed'})
    @app.post('/classifier-api/submissions/{identifier}/decision')
    def decide(identifier: str, payload: dict):
        return submissions.update(identifier, lambda row: row.update(status=payload['decision']))
    @app.post('/classifier-api/submissions/{identifier}/verify')
    def verify(identifier: str):
        result = {'result_label': '근거 부족'}
        submissions.update(identifier, lambda row: row.update(verification=result, review_revision=row.get('review_revision', 0) + 1))
        return result
    @app.patch('/postponements/{identifier}/approve')
    def approve(identifier: int):
        with factory() as db:
            row = db.get(Postponement, identifier)
            nested = client.post(f'/classifier-api/submissions/{row.classifier_submission_id}/decision', json={'decision': 'approved'})
            assert nested.status_code == 200
            row.status = 'approved'
            db.commit()
            return {'id': row.id, 'person_id': row.person_id, 'status': row.status}
    with TestClient(app) as client:
        assert client.post('/classifier-api/submissions', files={'file': ('가상.pdf', b'%PDF private document bytes', 'application/pdf')}).status_code == 202
        assert len(captured) == 1
        assert 'private document bytes' not in json.dumps(captured)
        assert captured[0]['details']['신청 구분'] == '연기'
        with factory() as db:
            db.add(Postponement(person_id='test-001', type='delay', reason='질병', classifier_submission_id='synthetic'))
            db.commit()
        assert client.patch('/postponements/1/approve').status_code == 200
        assert len(captured) == 2
        assert captured[1]['action'] == 'postponement.approve'
        assert captured[1]['details']['신청 구분'] == '연기'
        submissions.save({'id': 'unlinked', 'filename': '다른가상.pdf', 'military_number': '', 'applicant_name': '신청인',
                          'reason_category': '경찰관', 'application_type': 'statutory.police', 'status': 'pending', 'analysis_state': 'completed'})
        assert client.post('/classifier-api/submissions/unlinked/decision', json={'decision': 'declined'}).status_code == 200
        assert client.post('/classifier-api/submissions/unlinked/decision', json={'decision': 'declined'}).status_code == 200
        assert len(captured) == 3
        assert captured[2]['people'][0]['name'] == '신청인'
        assert captured[2]['details']['신청 구분'] == '보류'
        with factory() as db:
            db.add(Postponement(person_id='test-001', type='delay', reason='질병', classifier_submission_id='direct'))
            db.commit()
        submissions.save({'id': 'direct', 'military_number': 'test-001', 'applicant_name': '가상인원1',
                          'reason_category': '질병', 'status': 'pending', 'analysis_state': 'completed'})
        assert client.post('/classifier-api/submissions/direct/decision', json={'decision': 'declined'}).status_code == 200
        assert len(captured) == 4
        assert client.post('/classifier-api/submissions/direct/verify').status_code == 200
        assert client.post('/classifier-api/submissions/direct/verify').status_code == 200
        assert len(captured) == 6
        assert captured[-1]['action'] == 'postponement.document_verify'


def test_supported_business_write_routes_use_actual_prefixes():
    from user.app.api import organization, postponements, prosecution_documents, reservists, squads, training, training_results, transfers
    routers = [organization.router, postponements.router, prosecution_documents.router, reservists.router,
               reservists.persons_router, squads.router, training.router, training.persons_training_router,
               training_results.router, transfers.router]
    excluded = {'/postponements/resolve-applicant', '/postponements/verify',
                '/reservists/training-schedules/{schedule_id}/enable-demo-early-save'}
    for router in routers:
        for route in router.routes:
            for method in route.methods & {'POST', 'PATCH', 'PUT', 'DELETE'}:
                if route.path in excluded:
                    continue
                path = re.sub(r'\{[^}]+\}', '1', route.path)
                assert match_operation(method, path), f'{method} {route.path}'
    assert match_operation('GET', '/persons/1') is None
    assert match_operation('POST', '/copilot/chat') is None
    assert match_operation('POST', '/worklogs/today/confirm') is None


def test_log_writer_failure_does_not_turn_committed_write_into_error(environment, caplog):
    app, captured, factory = environment
    def fail(**event):
        raise OSError('disk full')
    app.user_middleware.clear()
    app.add_middleware(WorkLogMiddleware, session_factory=factory, writer=fail)
    @app.patch('/persons/{number}')
    def edit(number: str):
        with factory() as db:
            person = db.get(Person, number)
            person.name = '저장완료'
            db.commit()
            return {'military_number': number}
    with TestClient(app) as client:
        assert client.patch('/persons/test-001').status_code == 200
    with factory() as db:
        assert db.get(Person, 'test-001').name == '저장완료'
    assert 'Daily-log recording failed' in caplog.text
