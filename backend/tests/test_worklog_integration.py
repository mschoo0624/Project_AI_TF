"""Actual business API -> daily record -> archived PDF, using isolated databases."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from user.app import models
from user.app.api.reservists import persons_router
from user.app.database import get_db
from user.app.worklog.middleware import WorkLogMiddleware
from user.app.worklog.router import router


def test_person_change_is_visible_and_confirmation_preserves_prior_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKLOG_DB_PATH', str(tmp_path / 'journal.sqlite3'))
    engine = create_engine(f"sqlite:///{tmp_path / 'business.sqlite3'}", connect_args={'check_same_thread': False})
    models.Person.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(models.Person(military_number='worklog-test', name='가상인원', branch='육군', rank='병장',
                             service_year=5, position='소총수', status='active', mobilization_status='해당없음'))
        db.commit()
    app = FastAPI()
    app.include_router(persons_router)
    app.include_router(router)
    app.add_middleware(WorkLogMiddleware, session_factory=sessions)

    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            assert client.get('/worklogs/today').json()['events'] == []
            result = client.patch('/persons/worklog-test', json={'unit': '검증용 부대'})
            assert result.status_code == 200, result.text
            detail = client.get('/worklogs/today').json()
            assert len(detail['events']) == 1
            assert detail['events'][0]['people'][0]['name'] == '가상인원'
            assert detail['events'][0]['people'][0]['unit'] == '검증용 부대'
            day = detail['date']
            confirmed = client.post(f'/worklogs/{day}/confirm', json={
                'notes': '확인 완료', 'expected_event_id': detail['last_event_id'],
            })
            assert confirmed.status_code == 200, confirmed.text
            first_pdf = client.get(f'/worklogs/{day}/revisions/1/pdf').content
            with pymupdf.open(stream=first_pdf, filetype='pdf') as document:
                assert len(document) == 1
                text = ''.join(page.get_text() for page in document)
                assert '인원 관리 1건' in text and '확인 완료' in text
                assert '세부 처리 내역' not in text
            # A rejected request, a read and an unchanged write must not create work.
            assert client.patch('/persons/missing', json={'unit': '실패'}).status_code == 404
            assert client.get('/persons/worklog-test').status_code == 200
            assert client.patch('/persons/worklog-test', json={'unit': '검증용 부대'}).status_code == 200
            assert len(client.get('/worklogs/today').json()['events']) == 1
            assert client.patch('/persons/worklog-test', json={'unit': '다음 부대'}).status_code == 200
            newer = client.get('/worklogs/today').json()
            assert newer['has_unconfirmed_changes'] and len(newer['events']) == 2
            assert client.post(f'/worklogs/{day}/confirm', json={
                'notes': '', 'expected_event_id': detail['last_event_id'],
            }).status_code == 409
            saved = client.post(f'/worklogs/{day}/confirm', json={
                'notes': '추가 확인', 'expected_event_id': newer['last_event_id'],
            }).json()
            assert saved['revisions'][0]['revision'] == 2
            assert client.get(f'/worklogs/{day}/revisions/1/pdf').content == first_pdf
    finally:
        engine.dispose()
