"""Synthetic deterministic fixtures; no LLM calls or real applicant records."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import pytest

from fastapi.testclient import TestClient

from backend.classifier_agent.API import app
from backend.classifier_agent.verification import Evaluation, rules_catalog, verify_application


def document(kind, values, id='test-document'):
    text = '\n'.join(f'{k}: {str(v)}' for k, v in values.items())
    return {'document_id': id, 'application_type': kind, 'fields': {
        k: {'value': v, 'status': 'explicit_negative' if v is False else 'observed', 'errors': [],
            'evidence': [{'document_id': id, 'page': 1, 'quote': f'{k}: {str(v)}'}]}
        for k, v in values.items()},
        'pdf': {'status': 'extracted', 'pages': [{'number': 1, 'text': text}]}}


def context(**kwargs):
    base = {'applicant_name': '홍길동', 'applicant_service_number': '22-1',
            'documents_acceptable': True, 'training_scope_applicable': True,
            'training_start': '2026-05-10', 'training_end': '2026-05-10'}
    return {k: {'value': v, 'source': 'synthetic test fixture'} for k, v in (base | kwargs).items()}


def illness(**kwargs):
    return document('postponement.illness', {
        'subject_name': '홍길동', 'subject_service_number': '22-1', 'document_title': '입원확인서',
        'inpatient_status': True, 'admission_date': '2026-05-09', 'discharge_date': '2026-05-10'} | kwargs)


def test_inpatient_alternative_and_boundary():
    result = verify_application([illness()], context())
    assert result['result'] == 'sufficient'
    assert result['automatic_approval'] is False
    assert result['missing_information'] == []
    assert result['related_provisions'][0]['table'] == 7
    assert result['related_provisions'][0]['page'] == 1
    assert '입원' in result['related_provisions'][0]['page_text']
    # One failed alternative is not sufficient to reject all other alternatives.
    assert verify_application([illness(discharge_date='2026-05-09')], context())['result'] == 'insufficient'


def test_missing_not_false_and_partial_date():
    doc = illness(); del doc['fields']['discharge_date']
    result = verify_application([doc], context())
    assert result['result'] == 'insufficient'
    assert 'discharge_date' in result['missing_information']
    assert verify_application([illness(admission_date='2026-05')], context())['result'] == 'review_required'


def test_tampered_evidence_cannot_pass():
    doc = illness(); doc['fields']['inpatient_status']['evidence'][0]['quote'] = '없는 근거'
    assert verify_application([doc], context())['result'] == 'review_required'


def test_name_mismatch_and_wrong_number_not_masked_by_birthday():
    assert verify_application([illness(subject_name='김철수')], context())['result'] == 'not_met'
    doc = illness(subject_service_number='wrong', subject_birth_date='1990-01-01')
    assert verify_application([doc], context(applicant_birth_date='1990-01-01'))['result'] == 'not_met'


def test_death_has_no_caregiver_requirement():
    doc = document('postponement.family', {'subject_name': '홍길동', 'subject_service_number': '22-1',
        'relationship': '친조부', 'relationship_path': '가족관계 증명', 'death_date': '2026-05-04'})
    assert verify_application([doc], context(death_document_confirmed=True))['result'] == 'sufficient'
    # May 11 falls outside May 4..10 (7 inclusive days).
    result = verify_application([doc], context(death_document_confirmed=True, training_start='2026-05-11', training_end='2026-05-11'))
    assert result['result'] != 'sufficient'


def test_counts_missing_and_limit():
    doc = document('postponement.exam', {'subject_name': '홍길동', 'subject_service_number': '22-1',
        'exam_name': '기사시험', 'registration_date': '2026-05-01', 'exam_end': '2026-05-10'})
    assert verify_application([doc], context(exam_document_confirmed=True, exam_lifetime_count=5))['result'] == 'sufficient'
    assert verify_application([doc], context(exam_document_confirmed=True, exam_lifetime_count=6))['result'] == 'not_met'
    assert verify_application([doc], context(exam_document_confirmed=True))['result'] == 'insufficient'


def test_months_are_not_days():
    rule = {'id': 'duration', 'label': '기간', 'op': 'days_at_least', 'fields': ['treatment_duration'], 'days': 180}
    for text, expected in [('179일', 'fail'), ('180일', 'pass'), ('6개월', 'review')]:
        doc = document('policy.long_illness', {'treatment_duration': text})
        assert Evaluation([doc], {}).evaluate(rule)['status'] == expected


def test_conflicting_documents_and_unreadable_pages():
    assert verify_application([illness(), document('postponement.illness', {'subject_name': '다른 사람'}, 'second')], context())['result'] == 'review_required'
    doc = illness(); doc['pdf']['status'] = 'partial'
    assert verify_application([doc], context())['result'] == 'review_required'


def test_scanned_document_for_illness_is_insufficient_evidence():
    doc = document('postponement.illness', {})
    doc['pdf']['status'] = 'no_text'
    result = verify_application([doc], context())
    assert result['result'] == 'insufficient'
    assert result['result_label'] == '근거 부족'
    assert next(c for c in result['checks'] if c['id'] == 'document_completeness')['status'] == 'missing'


def test_all_types_have_references_and_no_default_pass():
    rules = rules_catalog()
    assert len(rules['types']) == 68
    for kind, rule in rules['types'].items():
        assert rule['citation']['page_text']
        assert verify_application([document(kind, {})], {})['result'] != 'sufficient'


def test_api_references_and_bad_inputs():
    client = TestClient(app)
    assert client.get('/verification-rules').status_code == 200
    response = client.post('/verify', json={'documents': [illness()], 'context': context()})
    assert response.status_code == 200 and response.json()['result'] == 'sufficient'
    assert client.get('/verification-sources/7').headers['content-type'] == 'application/pdf'
    assert client.get('/verification-sources/8').status_code == 404
    assert client.post('/verify', json={'documents': []}).status_code == 422
    assert client.post('/verify', json={'documents': [illness(), illness()]}).status_code == 422
    assert client.post('/verify', json={'documents': [illness()], 'context': {'x': {'value': True, 'source': ''}}}).status_code == 422


def test_source_change_blocks_conclusion(monkeypatch):
    from backend.classifier_agent import verification
    actual = verification.rules_catalog()
    actual['types']['postponement.illness']['citation']['sha256'] = 'changed'
    monkeypatch.setattr(verification, 'rules_catalog', lambda: actual)
    assert verification.verify_application([illness()], context())['result'] == 'review_required'


def test_age_uses_calendar_year_and_context_boolean_is_strict():
    rule = {'id': 'age', 'label': '41세', 'op': 'year_age',
            'fields': ['context.applicant_birth_date', 'context.assessment_date'], 'years': 41}
    assert Evaluation([], context(applicant_birth_date='1985-12-31', assessment_date='2026-01-01')).evaluate(rule)['status'] == 'pass'
    assert Evaluation([], context(applicant_birth_date='1986-01-01', assessment_date='2026-12-31')).evaluate(rule)['status'] == 'fail'
    rule = {'id': 'checked', 'label': '확인', 'op': 'equals', 'fields': ['context.checked'], 'value': True}
    assert Evaluation([], context(checked='true')).evaluate(rule)['status'] == 'review'
    rule = {'id': 'wedding', 'label': '결혼', 'op': 'point_window',
            'fields': ['event_date', 'context.training_start'], 'days': 14}
    for day, state in [('2026-05-24', 'pass'), ('2026-05-25', 'fail'), ('2026-04-26', 'pass'), ('2026-04-25', 'fail')]:
        assert Evaluation([document('postponement.family_event', {'event_date': day})], context()).evaluate(rule)['status'] == state


def test_business_api_reads_db_identity_without_guessing_history(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from user.app.api import postponements as api
    person = SimpleNamespace(name='DB 이름', military_number='db-id')
    education = SimpleNamespace(id=1, person_id='db-id', scheduled_date=date(2026, 5, 10))
    class DB:
        def get(self, model, key):
            return person if model is api.Person else education
    recorded = {}
    def verify(documents, facts):
        recorded.update(facts)
        return {'result': 'insufficient'}
    monkeypatch.setattr(api, 'verify_documents', verify)
    payload = api.VerificationInput(person_id='db-id', education_id=1, documents=[illness()],
                                    context={'applicant_name': {'value': 'tampered', 'source': 'caller'}})
    assert api.verify_postponement(payload, DB())['result'] == 'insufficient'
    assert recorded['applicant_name']['value'] == 'DB 이름'
    assert recorded['training_start']['value'] == '2026-05-10'
    assert 'training_end' not in recorded and 'exam_lifetime_count' not in recorded
    education.person_id = 'other'
    with pytest.raises(api.HTTPException) as exc:
        api.verify_postponement(payload, DB())
    assert exc.value.status_code == 404
