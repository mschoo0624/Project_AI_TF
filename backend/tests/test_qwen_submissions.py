"""Persistence and UI workflow integration. Extraction is stubbed, not an LLM evaluation."""
from pathlib import Path
import json
import sqlite3
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.classifier_agent import API as api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSIFIER_DATA_DIR', str(tmp_path/'store'))
    def extract(path, application_type, **kwargs):
        assert Path(path).read_bytes() == b'%PDF-fixture'
        return {'application_type': application_type, 'document_id': 'fixture', 'fields': {},
                'status': 'extracted', 'pdf': {'status': 'extracted', 'pages': [{'number': 1, 'text': 'fixture'}]}}
    monkeypatch.setattr(api, 'extract_application', extract)
    return TestClient(api.app)


def upload(client):
    response = client.post('/submissions', data={'application_type': 'postponement.illness',
        'military_number': '22-1', 'applicant_name': '홍길동'}, files={'file': ('medical.pdf', b'%PDF-fixture', 'application/pdf')})
    assert response.status_code == 200, response.text
    return response.json()


def test_optional_identity_and_archive(client):
    response = client.post('/submissions', data={'application_type': 'postponement.illness'},
                           files={'file': ('medical.pdf', b'%PDF-fixture', 'application/pdf')})
    assert response.status_code == 200
    item = response.json()
    assert item['military_number'] == ''
    result = client.post(f'/submissions/{item["id"]}/verify', json={'context': {}})
    assert result.status_code == 200
    assert result.json()['result'] != 'sufficient'
    response = client.post(f'/submissions/{item["id"]}/identity', json={'military_number': '22-1', 'applicant_name': '홍길동'})
    assert response.status_code == 200
    assert response.json()['verification'] is None
    assert client.post(f'/submissions/{item["id"]}/identity', json={'military_number': 'other', 'applicant_name': '다른 사람'}).status_code == 409
    api.submissions.update(item['id'], lambda row: row.update(archived=True))
    assert client.get('/submissions').json() == []
    assert client.get(f'/submissions/{item["id"]}/pdf').status_code == 200


def test_saved_pdf_verification_confirmation_and_human_decision(client):
    item = upload(client); id = item['id']
    assert client.get('/submissions').json()[0]['id'] == id
    assert client.get(f'/submissions/{id}/pdf').content == b'%PDF-fixture'
    facts = {'applicant_service_number': {'value': '22-1', 'source': 'person:22-1'}}
    result = client.post(f'/submissions/{id}/verify', json={'context': facts})
    assert result.status_code == 200
    assert result.json()['result'] != 'sufficient'
    assert client.get(f'/submissions/{id}').json()['verification'] == result.json()
    assert client.post(f'/submissions/{id}/request-confirmation', json={'note': '치료 기간 보완'}).status_code == 200
    assert client.get('/submissions').json()[0]['confirmation_requested'] is True
    # User explicitly retains human final approval, even when evidence is insufficient.
    approved = client.post(f'/submissions/{id}/decision', json={'decision': 'approved', 'note': '원본 확인 완료'})
    assert approved.json()['status'] == 'approved'
    assert approved.json()['note'] == '원본 확인 완료'
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 200
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'declined'}).status_code == 409
    assert client.post(f'/submissions/{id}/verify', json={'context': facts}).status_code == 409


def test_wrong_person_and_failed_extraction_cleanup(client, monkeypatch):
    item = upload(client)
    assert client.post(f'/submissions/{item["id"]}/verify', json={'context': {
        'applicant_service_number': {'value': 'other', 'source': 'person:other'}}}).status_code == 422
    def fail(*args, **kwargs): raise api.ModelError('test failure')
    monkeypatch.setattr(api, 'extract_application', fail)
    response = client.post('/submissions', data={'application_type': 'postponement.illness',
        'military_number': '22-1', 'applicant_name': '홍길동'}, files={'file': ('medical.pdf', b'%PDF-fixture')})
    assert response.status_code == 503
    assert len(list(api.submissions.root().glob('*.pdf'))) == 1
    assert len(client.get('/submissions').json()) == 1
    assert api.busy.acquire(blocking=False)
    api.busy.release()


def test_business_link_and_decision_are_persisted(client, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from user.app import models
    from user.app.api import postponements as business
    from user.app.database import Base, get_db
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(business.Person(military_number='22-1', name='홍길동', branch='육군', service_year=3, position='행정병'))
        db.commit()
        service = FastAPI(); service.include_router(business.router)
        service.dependency_overrides[get_db] = lambda: db
        monkeypatch.setattr(business, 'get_submission', lambda id: client.get(f'/submissions/{id}').json())
        def decide(id, decision, note=None):
            response = client.post(f'/submissions/{id}/decision', json={'decision': decision, 'note': note})
            response.raise_for_status(); return response.json()
        monkeypatch.setattr(business, 'decide_submission', decide)
        def verify(documents, context, id=None):
            response = client.post(f'/submissions/{id}/verify', json={'context': context})
            response.raise_for_status(); return response.json()
        monkeypatch.setattr(business, 'verify_documents', verify)
        app = TestClient(service); item = upload(client)
        # Name resolution uses only the newly extracted field, never the filename or legacy data.
        unresolved = {**item, 'military_number': '', 'extraction': {'fields': {
            'subject_name': {'value': '홍길동', 'status': 'observed'}}}}
        with monkeypatch.context() as patch:
            patch.setattr(business, 'get_submission', lambda id: unresolved)
            import httpx
            linked = []
            def identity(url, json, timeout):
                linked.append(json)
                return httpx.Response(200, json={**unresolved, **json}, request=httpx.Request('POST', url))
            patch.setattr(business.httpx, 'post', identity)
            resolved = app.post('/postponements/resolve-applicant', json={'submission_id': item['id']})
            assert resolved.json()['submission']['military_number'] == '22-1'
            db.add(business.Person(military_number='22-2', name='홍길동', branch='육군', service_year=3))
            db.commit()
            ambiguous = app.post('/postponements/resolve-applicant', json={'submission_id': item['id']})
            assert ambiguous.json()['submission']['military_number'] == ''
            assert len(linked) == 1
            unresolved['extraction']['fields']['subject_name']['status'] = 'conflicting'
            assert app.post('/postponements/resolve-applicant', json={'submission_id': item['id']}).json()['submission']['military_number'] == ''
            assert len(linked) == 1
        payload = {'person_id': '22-1', 'reason': 'caller reason', 'category': 'incorrect', 'classifier_submission_id': item['id']}
        first = app.post('/postponements', json=payload)
        assert first.status_code == 201, first.text
        id = first.json()['id']
        assert first.json()['category'] == 'postponement.illness'
        assert app.post('/postponements', json=payload).json()['id'] == id
        result = app.post('/postponements/verify', json={'person_id': '22-1', 'submission_id': item['id'], 'documents': [item['extraction']], 'context': {}})
        assert result.status_code == 200
        assert client.get(f'/submissions/{item["id"]}').json()['context']['applicant_name']['value'] == '홍길동'
        response = app.patch(f'/postponements/{id}/approve', json={'note': '담당자 확인'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'approved'
        assert app.patch(f'/postponements/{id}/approve', json={}).status_code == 200
        assert client.get(f'/submissions/{item["id"]}').json()['status'] == 'approved'
    engine.dispose()


def test_legacy_reprocessing_preserves_old_record_and_is_repeat_safe(client, tmp_path, monkeypatch):
    from backend.classifier_agent.reprocess_legacy import reprocess
    legacy = tmp_path/'legacy'; (legacy/'uploads').mkdir(parents=True)
    (legacy/'uploads'/'old.pdf').write_bytes(b'%PDF-fixture')
    old = {'id': 'old-id', 'military_number': '22-1', 'filename': 'old.pdf', 'saved_path': '/uploads/old.pdf', 'status': 'approved'}
    source = json.dumps(old)
    (legacy/'submissions.jsonl').write_text(source, encoding='utf-8')
    project = tmp_path/'project.sqlite'
    with sqlite3.connect(project) as db:
        db.execute('CREATE TABLE person (military_number TEXT, name TEXT)')
        db.execute('INSERT INTO person VALUES (?,?)', ('22-1', '홍길동'))
        db.execute('CREATE TABLE postponement (id INTEGER PRIMARY KEY, person_id TEXT, type TEXT, reason TEXT, status TEXT, category TEXT, source_file TEXT, classifier_submission_id TEXT UNIQUE)')
    first = reprocess('old-id', 'postponement.illness', legacy, project)
    def no_repeat(*args, **kwargs): raise AssertionError('Must not repeat model work')
    monkeypatch.setattr(api, 'extract_application', no_repeat)
    second = reprocess('old-id', 'postponement.illness', legacy, project)
    assert first['id'] == second['id']
    assert first['status'] == 'pending'
    assert first['legacy_original_status'] == 'approved'
    assert first['verification'] is not None
    assert (legacy/'submissions.jsonl').read_text(encoding='utf-8') == source
    with sqlite3.connect(project) as db:
        assert db.execute('SELECT COUNT(*) FROM postponement').fetchone()[0] == 1
