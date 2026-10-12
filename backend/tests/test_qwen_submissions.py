"""Persistence and UI workflow integration. Extraction is stubbed, not an LLM evaluation."""
from pathlib import Path
from threading import Event, Thread
from concurrent.futures import ThreadPoolExecutor
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
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(api, 'jobs', executor)
    monkeypatch.setattr(api, 'jobs_closed', False)
    monkeypatch.setattr(executor, 'submit', lambda *args: None)
    def unavailable(*args, **kwargs):
        import httpx
        raise httpx.ConnectError('isolated test: no business service')
    monkeypatch.setattr(api.httpx, 'post', unavailable)
    yield TestClient(api.app)
    executor.shutdown(wait=False, cancel_futures=True)


def test_integrated_router_preserves_all_endpoints_and_workflow(client):
    service = FastAPI(lifespan=api.lifespan)
    service.include_router(api.router, prefix='/classifier-api')
    standalone = api.app.openapi()['paths']
    integrated = service.openapi()['paths']
    for path, methods in standalone.items():
        assert integrated['/classifier-api'+path].keys() == methods.keys()
    with TestClient(service) as app:
        assert app.get('/classifier-api/application-types').status_code == 200
        assert app.get('/application-types').status_code == 404
        response = app.post('/classifier-api/submissions', data={'application_type': 'postponement.illness', 'military_number': '22-1'}, files={'file': ('sample.pdf', b'%PDF-fixture')})
        assert response.status_code == 202
        id = response.json()['id']
        assert app.post(f'/classifier-api/submissions/{id}/cancel').status_code == 200
        response = app.post('/classifier-api/submissions', data={'application_type': 'postponement.illness', 'military_number': '22-1'}, files={'file': ('sample.pdf', b'%PDF-fixture')})
        id = response.json()['id']
        api.analyze_submission(id)
        assert app.get(f'/classifier-api/submissions/{id}/pdf?download=true').content == b'%PDF-fixture'
        item = app.get(f'/classifier-api/submissions/{id}').json()
        assert app.post(f'/classifier-api/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 409
        checked = app.patch(f'/classifier-api/submissions/{id}/review-checks', json={'revision': item['review_revision'], 'checks': {row['id']: True for row in item['review_items']}})
        assert checked.status_code == 200
        assert app.post(f'/classifier-api/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 200
        assert app.post(f'/classifier-api/submissions/{id}/reanalyze').status_code == 202
    saved = api.submissions.get(id)
    assert saved['analysis_state'] == 'failed'
    assert saved['status'] == 'approved'
    assert api.jobs_closed is True


def test_internal_client_targets_integrated_routes_and_rejects_legacy(monkeypatch):
    import httpx
    from user.app.services import classifier_client as connection
    calls = []
    def response(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={}, request=httpx.Request('POST', url))
    monkeypatch.setattr(connection.httpx, 'get', response)
    monkeypatch.setattr(connection.httpx, 'post', response)
    id = 'qwen_'+'a'*32
    connection.get_submission(id)
    connection.verify_documents([], {}, id)
    connection.decide_submission(id, 'approved')
    assert calls == [f'http://127.0.0.1:8002/classifier-api/submissions/{id}', f'http://127.0.0.1:8002/classifier-api/submissions/{id}/verify', f'http://127.0.0.1:8002/classifier-api/submissions/{id}/decision']
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        connection.decide_submission('legacy-id', 'approved')
    assert error.value.status_code == 422 and len(calls) == 3


def test_main_server_connects_classifier_lifecycle_and_routes(client, monkeypatch):
    import sys
    import importlib
    from types import ModuleType
    from fastapi import APIRouter
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    # Exercise the actual main app; bypass unrelated model loading and real DB writes.
    monkeypatch.setitem(sys.modules, 'classifier_agent.API', api)
    rag = ModuleType('RAG.legalrag.server')
    rag.router = APIRouter()
    rag.start_loading = lambda: None
    monkeypatch.setitem(sys.modules, 'RAG.legalrag.server', rag)
    main = importlib.import_module('user.app.main')
    for name in ('init_db', 'initialize_prediction_cache', 'initialize_attendance_cache', '_reconcile_due_training_records'):
        monkeypatch.setattr(main, name, lambda: None)
    pending = enqueue(client)
    with TestClient(main.app) as integrated:
        assert integrated.get('/classifier-api/application-types').status_code == 200
        assert integrated.get(f'/classifier-api/submissions/{pending["id"]}').json()['analysis_state'] == 'failed'
        response = integrated.post('/classifier-api/submissions', data={'application_type': 'postponement.illness'}, files={'file': ('test.pdf', b'%PDF-fixture')})
        assert response.status_code == 202
        id = response.json()['id']
    assert api.submissions.get(id)['analysis_state'] == 'failed'
    assert api.jobs_closed


def upload(client):
    response = client.post('/submissions', data={'application_type': 'postponement.illness',
        'military_number': '22-1', 'applicant_name': '홍길동'}, files={'file': ('medical.pdf', b'%PDF-fixture', 'application/pdf')})
    assert response.status_code == 202, response.text
    api.analyze_submission(response.json()['id'])
    return client.get(f'/submissions/{response.json()["id"]}').json()


@pytest.mark.parametrize('start,end,expected', [
    ('2026-05-01', '2026-05-11', True),
    ('2026-05-13', '2026-05-20', True),
    ('2026-05-01', '2026-05-10', False),
    ('2026-05-14', '2026-05-20', False),
    ('2026-05-20', '2026-05-01', False),
    (None, None, False),
])
def test_training_overlap_uses_display_dates_without_saving_context(client, start, end, expected):
    from test_verification import document
    item = upload(client)
    values = {} if start is None else {'admission_date': start, 'discharge_date': end}
    api.submissions.update(item['id'], lambda row: row.update(extraction=document('postponement.illness', values)))
    before = api.submissions.get(item['id'])
    response = client.get(f"/submissions/{item['id']}/training-overlap?start=2026-05-11&end=2026-05-13")
    assert response.status_code == 200
    assert response.json()['overlaps'] is expected
    assert api.submissions.get(item['id']) == before


@pytest.mark.parametrize('kind', ['postponement.illness', 'postponement.exam', 'policy.long_illness'])
def test_provision_view_highlights_only_matching_rule_row(client, kind):
    response = client.get(f'/verification-view/{kind}')
    assert response.status_code == 200
    page = response.json()
    if kind == 'postponement.illness':
        assert page['page'] == 1 and page['reason_number'] == '1'
    if kind == 'policy.long_illness':
        assert page['reason_number'] is None
    assert len(page['boxes']) == 1
    x0, y0, x1, y1 = page['boxes'][0]
    assert 0 <= x0 < x1 <= page['width']
    assert 0 <= y0 < y1 <= page['height']
    image = client.get(f"/verification-sources/{page['table']}/pages/{page['page']}/image")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert client.get('/verification-view/unknown').status_code == 404


def check_all(client, id):
    item = client.get(f'/submissions/{id}').json()
    response = client.patch(f'/submissions/{id}/review-checks', json={
        'checks': {entry['id']: True for entry in item['review_items']}, 'revision': item['review_revision']})
    assert response.status_code == 200, response.text


def test_optional_identity_and_archive(client):
    response = client.post('/submissions', data={'application_type': 'postponement.illness'},
                           files={'file': ('medical.pdf', b'%PDF-fixture', 'application/pdf')})
    assert response.status_code == 202
    item = response.json()
    api.analyze_submission(item['id'])
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
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 409
    check_all(client, id)
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
    assert response.status_code == 202
    api.analyze_submission(response.json()['id'])
    assert client.get(f'/submissions/{response.json()["id"]}').json()['analysis_state'] == 'failed'
    assert len(list(api.submissions.root().glob('*.pdf'))) == 2
    assert len(client.get('/submissions').json()) == 2
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
        assert app.post('/postponements', json={'person_id': '22-1', 'reason': 'missing type'}).status_code == 422
        assert app.post('/postponements', json={'person_id': '22-1', 'reason': 'legacy', 'category': 'postponement.illness', 'classifier_submission_id': 'legacy'}).status_code == 422
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
        assert app.patch(f'/postponements/{id}/approve', json={'note': '담당자 확인'}).status_code == 409
        check_all(client, item['id'])
        response = app.patch(f'/postponements/{id}/approve', json={'note': '담당자 확인'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'approved'
        assert app.patch(f'/postponements/{id}/approve', json={}).status_code == 200
        assert client.get(f'/submissions/{item["id"]}').json()['status'] == 'approved'
    engine.dispose()


def enqueue(client):
    response = client.post('/submissions', data={'application_type': 'postponement.illness', 'military_number': '22-1'},
                           files={'file': ('test.pdf', b'%PDF-fixture')})
    assert response.status_code == 202
    return response.json()


def test_submission_is_saved_before_analysis_and_queued_cancel_prevents_work(client, monkeypatch):
    monkeypatch.setattr(api, 'extract_application', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    item = enqueue(client)
    assert item['analysis_state'] == 'queued'
    assert client.get('/submissions').json()[0]['id'] == item['id']
    assert client.get(f'/submissions/{item["id"]}/pdf').content == b'%PDF-fixture'
    assert client.post(f'/submissions/{item["id"]}/decision', json={'decision': 'approved'}).status_code == 409
    assert client.post(f'/submissions/{item["id"]}/cancel').json()['analysis_state'] == 'cancelled'
    api.analyze_submission(item['id'])
    assert client.get(f'/submissions/{item["id"]}').json()['analysis_state'] == 'cancelled'


def test_cancel_during_work_does_not_publish_late_result(client, monkeypatch):
    started, finish = Event(), Event()
    original = api.extract_application
    def slow(*args, **kwargs):
        started.set()
        assert finish.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(api, 'extract_application', slow)
    item = enqueue(client)
    worker = Thread(target=api.analyze_submission, args=(item['id'],))
    worker.start()
    try:
        assert started.wait(3)
        assert client.get(f'/submissions/{item["id"]}').json()['analysis_state'] == 'analyzing'
        assert client.post(f'/submissions/{item["id"]}/cancel').status_code == 200
    finally:
        finish.set(); worker.join(3)
    saved = client.get(f'/submissions/{item["id"]}').json()
    assert not worker.is_alive()
    assert saved['analysis_state'] == 'cancelled'
    assert saved['extraction']['fields'] == {}
    assert saved['verification'] is None


def test_server_restart_marks_interrupted_jobs_retryable(client):
    item = enqueue(client)
    with TestClient(api.app) as restarted:
        assert restarted.get(f'/submissions/{item["id"]}').json()['analysis_state'] == 'failed'
        assert restarted.post(f'/submissions/{item["id"]}/retry').json()['analysis_state'] == 'queued'
        api.analyze_submission(item['id'])
        assert restarted.get(f'/submissions/{item["id"]}').json()['analysis_state'] == 'completed'


def test_checks_persist_reject_stale_updates_and_reset_on_reverification(client):
    item = upload(client); id = item['id']
    assert len(item['review_items']) == 5
    assert client.patch(f'/submissions/{id}/review-checks', json={'checks': {'invented': True}, 'revision': 0}).status_code == 422
    assert client.patch(f'/submissions/{id}/review-checks', json={'checks': {'identity': True}, 'revision': item['review_revision']}).status_code == 200
    assert client.patch(f'/submissions/{id}/review-checks', json={'checks': {'identity': False}, 'revision': item['review_revision']}).status_code == 409
    check_all(client, id)
    assert all(client.get(f'/submissions/{id}').json()['review_checks'].values())
    assert client.post(f'/submissions/{id}/verify', json={'context': {'applicant_service_number': {'value': '22-1', 'source': 'DB'}}}).status_code == 200
    assert client.get(f'/submissions/{id}').json()['review_checks'] == {}
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 409
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'declined', 'note': '근거 부족'}).status_code == 200


def test_pdf_page_image_and_page_bounds(client):
    item = upload(client)
    path = Path(__file__).resolve().parents[2]/'frontend/public/pdfs/홍길동.pdf'
    (api.submissions.root()/(item['id']+'.pdf')).write_bytes(path.read_bytes())
    response = client.get(f'/submissions/{item["id"]}/pages/1/image')
    assert response.status_code == 200
    assert response.content.startswith(b'\x89PNG')
    assert client.get(f'/submissions/{item["id"]}/pages/0/image').status_code == 404
    assert client.get(f'/submissions/{item["id"]}/pages/999/image').status_code == 404


def test_download_keeps_original_filename_and_preview_stays_inline(client):
    from urllib.parse import quote
    item = upload(client); id = item['id']
    filename = '홍길동 진단서.pdf'
    api.submissions.update(id, lambda row: row.update(filename=filename))
    response = client.get(f'/submissions/{id}/pdf?download=true')
    assert response.status_code == 200
    assert response.content == b'%PDF-fixture'
    assert response.headers['content-disposition'] == "attachment; filename*=utf-8''" + quote(filename)
    preview = client.get(f'/submissions/{id}/pdf')
    assert 'attachment' not in preview.headers.get('content-disposition', '')


def test_reanalysis_reuses_pdf_resets_checks_and_blocks_review_until_done(client):
    item = upload(client); id = item['id']
    check_all(client, id)
    response = client.post(f'/submissions/{id}/reanalyze')
    assert response.status_code == 202
    queued = response.json()
    assert queued['analysis_state'] == 'queued' and queued['reanalysis'] is True
    assert queued['review_checks'] == {}
    assert queued['extraction'] == item['extraction']  # original preview remains available
    assert client.post(f'/submissions/{id}/reanalyze').status_code == 409
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 409
    assert client.patch(f'/submissions/{id}/review-checks', json={'checks': {}, 'revision': queued['review_revision']}).status_code == 409
    api.analyze_submission(id)
    completed = client.get(f'/submissions/{id}').json()
    assert completed['analysis_state'] == 'completed'
    assert completed['review_revision'] > queued['review_revision']
    assert completed['status'] == 'pending' and completed['review_checks'] == {}
    assert client.get(f'/submissions/{id}/pdf').content == b'%PDF-fixture'


def test_cancelled_reanalysis_can_retry_without_old_run_overwriting_new_one(client, monkeypatch):
    item = upload(client); id = item['id']
    client.post(f'/submissions/{id}/reanalyze')
    started, release = Event(), Event()
    original = api.extract_application
    def slow(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(api, 'extract_application', slow)
    worker = Thread(target=api.analyze_submission, args=(id,)); worker.start()
    try:
        assert started.wait(3)
        assert client.post(f'/submissions/{id}/cancel').status_code == 200
        assert client.post(f'/submissions/{id}/retry').status_code == 200
    finally:
        release.set(); worker.join(3)
    assert not worker.is_alive()
    assert client.get(f'/submissions/{id}').json()['analysis_state'] == 'queued'
    api.analyze_submission(id)
    assert client.get(f'/submissions/{id}').json()['analysis_state'] == 'completed'


def test_reanalysis_does_not_revoke_final_decision(client):
    item = upload(client); id = item['id']
    check_all(client, id)
    assert client.post(f'/submissions/{id}/decision', json={'decision': 'approved'}).status_code == 200
    approved_at = client.get(f'/submissions/{id}').json()['decided_at']
    from datetime import datetime
    assert datetime.fromisoformat(approved_at).utcoffset().total_seconds() == 0
    assert client.post(f'/submissions/{id}/reanalyze').status_code == 202
    api.analyze_submission(id)
    assert client.get(f'/submissions/{id}').json()['status'] == 'approved'
    assert client.get(f'/submissions/{id}').json()['decided_at'] == approved_at
