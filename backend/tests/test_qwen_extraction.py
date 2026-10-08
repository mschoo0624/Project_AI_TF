import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.classifier_agent import extraction as ex
from backend.classifier_agent.API import app


def test_all_types_resolve():
    for key in ex.catalog()[1]:
        assert ex.selected_fields(key)[1]
    with pytest.raises(ValueError):
        ex.selected_fields('unknown')


def test_evidence_and_date():
    page = {'number': 1, 'text': '재직 2019-03. 발급 2026년 04월 19일'}
    field = {'type': 'date'}
    invalid = ex.validate_field({'value': '2019-03-01', 'evidence': ['재직 2019-03']}, field, page, 'id')
    assert invalid['value'] is None and 'date_not_supported' in invalid['errors']
    valid = ex.validate_field({'value': '2026-04-19', 'evidence': ['2026년 04월 19일']}, field, page, 'id')
    assert valid['status'] == 'observed'
    invalid = ex.validate_field({'value': False, 'evidence': ['없는 원문']}, {'type': 'boolean'}, page, 'id')
    assert invalid['status'] == 'invalid'


def test_employment_issue_date_with_incomplete_model_quote():
    pdf = Path(__file__).resolve().parents[2] / 'frontend/public/pdfs/old/employment.pdf'
    def client(messages):
        payload = json.loads(messages[1]['content'])
        output = {key: {'value': None, 'evidence': []} for key in payload['requested_fields']}
        if 'issued_on' in output:
            output['issued_on'] = {'value': '2026-04-19', 'evidence': ['발급일자 : 04월 19일']}
        return json.dumps(output)
    result = ex.extract_application(pdf, 'statutory.police', client=client)
    assert 'issued_on' not in result['fields']


def test_every_type_extracts_exactly_rule_references():
    from backend.classifier_agent.verification import rules_catalog
    rules = rules_catalog()
    common, types = ex.catalog()
    used = set()
    for kind in types:
        required = ex.rule_fields(rules['types'][kind].get('common', rules['common'])) | ex.rule_fields(rules['types'][kind]['checks']) | ex.rule_fields(rules['types'][kind].get('review_items', []))
        selected = ex.selected_fields(kind)[1]
        assert set(selected) == required, kind
        assert not any(k.startswith('context.') for k in selected)
        used.update(required)
    assert set(common['fields']) == used
    assert all(set(keys) <= used for keys in common['field_groups'].values())
    assert len(ex.selected_fields('postponement.illness')[1]) == 13
    assert sum(f.get('extraction') != 'layout' for f in ex.selected_fields('postponement.illness')[1].values()) == 8
    assert len(ex.selected_fields('postponement.exam')[1]) == 10
    assert 'treatment_duration' not in ex.selected_fields('postponement.illness')[1]
    assert 'treatment_opinion' in ex.selected_fields('policy.long_illness')[1]


def test_explicit_issue_date_does_not_invent_or_accept_invalid_dates():
    spec = {'type': 'date'}
    for text in ['발급일자 : 2026년 04월', '재직기간 2026년 04월 19일', '발급일자 : 04월 19일']:
        assert ex.explicit_issue_dates({'number': 1, 'text': text}, spec, 'id') == []
    bad = ex.explicit_issue_dates({'number': 1, 'text': '발급일자 : 2026년 02월 30일'}, spec, 'id')
    assert bad[0]['status'] == 'invalid'
    dates = ex.explicit_issue_dates({'number': 1, 'text': '발급일자 : 2026-04-19\n발급일자 : 2026-04-20'}, spec, 'id')
    assert [item['value'] for item in dates] == ['2026-04-19', '2026-04-20']


def test_missing_is_not_false_and_rejects_types():
    page = {'number': 1, 'text': '입원하지 않음'}
    field = {'type': 'boolean'}
    missing = ex.validate_field({'value': None, 'evidence': []}, field, page, 'id')
    negative = ex.validate_field({'value': False, 'evidence': ['입원하지 않음']}, field, page, 'id')
    wrong = ex.validate_field({'value': 'false', 'evidence': ['입원하지 않음']}, field, page, 'id')
    assert missing['status'] == 'missing'
    assert negative['status'] == 'explicit_negative'
    assert wrong['value'] is None and wrong['status'] == 'invalid'


def test_context_limit_before_network():
    with pytest.raises(ValueError, match='문맥'):
        ex.ask_qwen([{'role': 'user', 'content': '가' * 4000}])


def test_pipeline_conflicts_and_missing(tmp_path, monkeypatch):
    pdf = tmp_path / 'test.pdf'; pdf.write_bytes(b'pdf')
    monkeypatch.setattr(ex, 'extract_pdf', lambda _: {'status': 'extracted', 'pages': [
        {'number': 1, 'text': '성명 홍길동'}, {'number': 2, 'text': '성명 김철수'}]})
    def client(messages):
        data = json.loads(messages[1]['content'])
        output = {key: {'value': None, 'evidence': []} for key in data['requested_fields']}
        if 'subject_name' in output:
            output['subject_name'] = {'value': data['document'][3:], 'evidence': [data['document']]}
        return json.dumps(output)
    result = ex.extract_application(pdf, 'postponement.illness', client=client)
    assert result['fields']['subject_name']['status'] == 'conflicting'
    assert result['fields']['subject_name']['value'] is None
    assert result['status'] == 'needs_review'
    assert result['eligibility_decision'] is None
    failed = ex.extract_application(pdf, 'postponement.illness', client=lambda _: '{}')
    assert failed['status'] == 'needs_review'
    assert failed['fields']['subject_name']['status'] == 'invalid'


def test_api_rejects_unknown_type_and_invalid_pdf():
    client = TestClient(app)
    assert client.get('/application-types').status_code == 200
    assert client.post('/extract-pdf', data={'application_type': 'unknown'}, files={'file': ('x.pdf', b'abc')}).status_code == 422
    assert client.post('/extract-pdf', data={'application_type': 'postponement.illness'}, files={'file': ('x.pdf', b'abc')}).status_code == 422
