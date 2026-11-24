from datetime import datetime, timezone
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymupdf as fitz
import pytest

from user.app.worklog import repository
from user.app.worklog.pdf import render_pdf, template_path
from user.app.worklog.router import router


@pytest.fixture
def environment(tmp_path, monkeypatch):
    path = tmp_path / 'worklogs.sqlite3'
    monkeypatch.setenv('WORKLOG_DB_PATH', str(path))
    monkeypatch.delenv('WORKLOG_TEMPLATE_PATH', raising=False)
    monkeypatch.setattr(repository, 'now', lambda: datetime(2026, 11, 24, 14, 30, tzinfo=repository.KST))
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client, path


def record(**kwargs):
    return repository.append_event(**{
        'category': 'postponement', 'action': 'approve', 'summary': '질병 연기 승인',
        'actor': '가상담당자', 'people': [{'name': '가상대상자', 'military_number': 'test-001', 'rank': '병장'}],
        'details': {'reason': '가상 질병 치료', 'status': '승인'}, **kwargs,
    })


def test_initialize_today_persists_empty_day_without_fake_events(environment):
    client, path = environment
    repository.initialize()
    result = client.get('/worklogs/today').json()
    assert result['date'] == '2026-11-24'
    assert result['events'] == [] and result['revisions'] == []
    assert result['has_unconfirmed_changes'] is True
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM worklog_day').fetchone()[0] == 1
    assert client.get('/worklogs').json()[0]['event_count'] == 0


def test_event_snapshot_is_independent_and_idempotent(environment):
    people = [{'name': '최초 성명', 'military_number': 'test-002'}]
    original = record(people=people, dedupe_key='request-1')
    people[0]['name'] = '수정 성명'
    repeated = record(people=people, dedupe_key='request-1')
    assert repeated == original
    assert repository.get_day(original['date'])['events'][0]['people'][0]['name'] == '최초 성명'
    assert len(repository.get_day(original['date'])['events']) == 1


def test_utc_times_are_assigned_to_korean_calendar_day(environment):
    event = record(occurred_at=datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc))
    assert event['date'] == '2026-11-25'
    assert event['occurred_at'].startswith('2026-11-25T01:00:00+09:00')
    assert repository.ensure_today()['events'] == []


def test_confirm_stores_real_pdf_and_unchanged_repeat_reuses_revision(environment):
    client, path = environment
    event = record()
    payload = {'notes': '검토 완료', 'expected_event_id': event['id']}
    response = client.post('/worklogs/2026-11-24/confirm', json=payload)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['revisions'][0]['revision'] == 1
    assert detail['has_unconfirmed_changes'] is False
    assert detail['revisions'][0]['confirmed_by'] == '미인증 요청'
    pdf = client.get('/worklogs/2026-11-24/revisions/1/pdf')
    assert pdf.headers['content-type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF-')
    with fitz.open(stream=pdf.content, filetype='pdf') as document:
        assert document[0].rect == fitz.Rect(0, 0, 910, 1280)
        assert len(document) == 1
        assert len(document[0].get_drawings()) > 50  # original form retained
        text = '\n'.join(page.get_text() for page in document)
        for expected in ('가상대상자', '보류·연기 처리 1건', '검토 완료'):
            assert expected in text
        for removed in ('세부 처리 내역', '별첨', '다음 쪽', 'test-001', '가상 질병 치료'):
            assert removed not in text
    assert client.post('/worklogs/2026-11-24/confirm', json=payload).json()['revisions'] == detail['revisions']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM worklog_revision').fetchone()[0] == 1


def test_new_events_add_revision_without_overwriting_old_pdf(environment):
    client, _ = environment
    original = record()
    repository.confirm(original['date'], notes='', expected_event_id=original['id'], actor='tester')
    first_pdf = repository.get_pdf(original['date'], 1)
    next_event = record(summary='두 번째 처리')
    assert repository.get_day(original['date'])['has_unconfirmed_changes'] is True
    second = repository.confirm(original['date'], notes='추가 확인', expected_event_id=next_event['id'], actor='tester')
    assert [revision['revision'] for revision in second['revisions']] == [2, 1]
    assert second['revisions'][0]['event_count'] == 2
    assert repository.get_pdf(original['date'], 1) == first_pdf
    assert b'%PDF-' == repository.get_pdf(original['date'], 2)[:5]


def test_stale_confirmation_is_rejected_without_partial_storage(environment):
    client, path = environment
    event = record()
    record(summary='화면 조회 후 추가된 업무')
    response = client.post('/worklogs/2026-11-24/confirm', json={'notes': '미확인 메모', 'expected_event_id': event['id']})
    assert response.status_code == 409
    detail = client.get('/worklogs/2026-11-24').json()
    assert detail['revisions'] == [] and detail['notes'] == ''
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM worklog_revision').fetchone()[0] == 0


def test_missing_template_rolls_back_confirmation(environment, monkeypatch, tmp_path):
    client, _ = environment
    record()
    monkeypatch.setenv('WORKLOG_TEMPLATE_PATH', str(tmp_path / 'missing.pdf'))
    response = client.post('/worklogs/2026-11-24/confirm', json={'notes': '저장되지 않아야 함', 'expected_event_id': 1})
    assert response.status_code == 503
    assert repository.get_day('2026-11-24')['revisions'] == []
    assert repository.get_day('2026-11-24')['notes'] == ''


def test_template_and_missing_records(environment):
    client, _ = environment
    assert client.get('/worklogs/template').content == template_path().read_bytes()
    assert client.get('/worklogs/2020-01-01').status_code == 404
    assert client.get('/worklogs/not-a-date').status_code == 422
    assert client.get('/worklogs/2026-11-24/revisions/99/pdf').status_code == 404


def test_pdf_stays_within_original_form_even_with_many_events_and_long_notes(environment):
    for index in range(30):
        record(category='transfer_in', summary=f'전입 처리 {index}', people=[{
            'name': f'가상전입자{index:03d}', 'military_number': f'synthetic-{index:03d}',
            'unit': '가상부대 ' * 12,
        }], details={'reason': '긴 설명 검증 ' * 40})
    snapshot = repository.get_day('2026-11-24')
    snapshot['notes'] = ('줄바꿈과 긴 비고를 검증합니다.\n' * 100) + '비고의 마지막 문장'
    pdf = render_pdf(snapshot, revision=1, confirmed_by='tester')
    with fitz.open(stream=pdf, filetype='pdf') as document:
        assert len(document) == 1
        text = '\n'.join(page.get_text() for page in document)
        assert '가상전입자000' in text and '가상전입자010' in text
        assert '비고:' in text
        assert '…' in text
        for removed in ('세부 처리 내역', '별첨', '다음 쪽', '긴 설명 검증'):
            assert removed not in text


def test_empty_day_can_be_confirmed_and_notes_change_adds_revision(environment):
    client, _ = environment
    client.get('/worklogs/today')
    empty = client.post('/worklogs/2026-11-24/confirm', json={'notes': '', 'expected_event_id': 0}).json()
    assert empty['revisions'][0]['event_count'] == 0
    updated = client.post('/worklogs/2026-11-24/confirm', json={'notes': '업무 없음 확인', 'expected_event_id': 0}).json()
    assert updated['revisions'][0]['revision'] == 2


def test_postponement_type_is_written_in_eighth_column_on_both_halves(environment):
    details = [
        {'신청 구분': '보류'},
        {'신청 구분': '연기'},
        {'변경 항목': [{'항목': '신청 구분', '이후': 'hold'}]},
        {},
        {'변경 항목': [{'항목': '신청 유형', '이후': 'postponement.illness'}]},
        {'신청 구분': '보류'},
    ]
    for item in details:
        record(details=item)
    pdf = render_pdf(repository.get_day('2026-11-24'), revision=1, confirmed_by='tester')
    with fitz.open(stream=pdf, filetype='pdf') as document:
        for index, expected in enumerate(['보류', '연기', '보류', '보류/연기', '연기', '보류']):
            left = 440 + 405 * (index // 4)
            top = 1110 + 30 * (index % 4)
            assert document[0].get_textbox(fitz.Rect(left, top, left + 50, top + 30)).strip() == expected


def test_preview_uses_unsaved_notes_without_changing_persisted_record(environment):
    client, path = environment
    event = record()
    day = event['date']
    client.post(f'/worklogs/{day}/confirm', json={'notes': '기존 저장 비고', 'expected_event_id': event['id']})
    with sqlite3.connect(path) as db:
        before = list(db.iterdump())
    response = client.post(f'/worklogs/{day}/preview', json={'notes': '아직 저장하지 않은 비고', 'expected_event_id': event['id']})
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    with fitz.open(stream=response.content, filetype='pdf') as document:
        assert len(document) == 1
        text = '\n'.join(page.get_text() for page in document)
        assert '아직 저장하지 않은 비고' in text
        assert '기존 저장 비고' not in text
        assert '가상대상자' in text
        assert '미리보기 · 저장 전' in text
        assert '저장본' not in text and '확인 시각' not in text and '확인자' not in text
        assert '미리보기' in document.metadata['title']
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before


def test_empty_preview_does_not_create_a_saved_revision(environment):
    client, path = environment
    detail = client.get('/worklogs/today').json()
    response = client.post(f"/worklogs/{detail['date']}/preview", json={'notes': '', 'expected_event_id': 0})
    assert response.status_code == 200
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM worklog_revision').fetchone()[0] == 0
        assert db.execute('SELECT notes FROM worklog_day').fetchone()[0] == ''


def test_preview_rejects_missing_day_stale_events_and_missing_template(environment, monkeypatch, tmp_path):
    client, path = environment
    assert client.post('/worklogs/2020-01-01/preview', json={'notes': '', 'expected_event_id': 0}).status_code == 404
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM worklog_day').fetchone()[0] == 0
    first = record()
    second = record(summary='새 업무')
    assert client.post(f"/worklogs/{first['date']}/preview", json={'notes': '미저장 비고', 'expected_event_id': first['id']}).status_code == 409
    monkeypatch.setenv('WORKLOG_TEMPLATE_PATH', str(tmp_path / 'missing.pdf'))
    assert client.post(f"/worklogs/{first['date']}/preview", json={'notes': '미저장 비고', 'expected_event_id': second['id']}).status_code == 503
    detail = repository.get_day(first['date'])
    assert detail['notes'] == '' and detail['revisions'] == []
