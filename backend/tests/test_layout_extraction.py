import json
from pathlib import Path

from backend.classifier_agent import extraction as ex
from backend.classifier_agent.layout import dates
from backend.classifier_agent.pdf_extract import extract_pdf


def test_spaced_date_validation_and_no_invented_day():
    assert dates('2 0 2 6 년 0 4 월 1 6 일')[0][0] == '2026-04-16'
    assert dates('2026년 4월') == []
    assert dates('2026년 2월 30일') == []
    p = {'number': 1, 'text': '2 0 2 6 년 0 4 월 1 6 일'}
    result = ex.validate_field({'value': '2026-04-16', 'evidence': [p['text']]}, {'type': 'date'}, p, 'd')
    assert result['status'] == 'observed'


def test_evidence_ids_keep_exact_cell_quote_and_coordinates():
    source = {'id': 'p1s1', 'text': '약 8주의 안정 및\n가료가 필요', 'bbox': [1,2,3,4], 'kind': 'cell'}
    p = {'number': 1, 'text': '원문 읽기 순서가 다른 페이지', 'sources': [source]}
    item = {'value': '약 8주', 'evidence_ids': ['p1s1']}
    result = ex.resolve_field(item, {'type': 'string'}, p, 'doc', {'p1s1': source})
    assert result['status'] == 'observed'
    assert result['evidence'][0]['quote'] == source['text']
    assert result['evidence'][0]['bbox'] == source['bbox']
    item['evidence_ids'] = ['invented']
    assert ex.resolve_field(item, {'type': 'string'}, p, 'doc', {'p1s1': source})['value'] is None


def test_whitespace_only_matching_does_not_accept_missing_words():
    p = {'number': 1, 'text': '진단일로부터 약 8주의 안정 및\n가료가 필요합니다.'}
    good = ex.validate_field({'value': '8주', 'evidence': ['진단일로부터 약 8주의 안정 및 가료가 필요합니다.']}, {'type': 'string'}, p, 'd')
    assert good['status'] == 'observed'
    assert '\n' in good['evidence'][0]['quote']
    bad = ex.validate_field({'value': '8주', 'evidence': ['약 8주의 가료가 필요합니다.']}, {'type': 'string'}, p, 'd')
    assert bad['status'] == 'invalid'


def test_role_checks_block_observed_model_mistakes():
    examples = [
        ('issuer_name', '2026-000184', '등록번호\n2026-000184', '', 'string'),
        ('diagnosis', '임상적 추정', '위와 같이 진단합니다.', '', 'string'),
        ('treatment_start', '2026-04-16', '2026년 4월 16일', '진단 연월일', 'date'),
        ('registration_date', '2026-02-12', '2026년 2월 12일', '발급일', 'date'),
        ('treatment_duration', '6주', '6주간 고정, 8주의 안정 및 가료', '치료 소견', 'string'),
        ('document_number', '제2차시험', '제2차시험', '', 'string'),
        ('verification_reference', 'SAM', 'SAMPLE', '', 'string'),
        ('exam_stage', '1교시, 2교시', '1교시, 2교시', '', 'string'),
        ('next_stage_date', '2026-02-22', '2026.02.22(일)', '시험일', 'date'),
    ]
    for key, value, text, label, kind in examples:
        s = {'id':'s1', 'text':text, 'label':label, 'kind':'cell'}
        p = {'number':1, 'text':text, 'sources':[s]}
        result = ex.resolve_field({'value':value, 'evidence_ids':['s1']}, {'type':kind}, p, 'doc', {'s1':s})
        ex.validate_role(key, result, {'s1':s})
        assert result['status'] == 'invalid', key
        assert result['value'] is None
        assert result['evidence']


def test_issue_date_uses_issuer_footer_not_exam_schedule():
    p = {'number':1, 'height':600, 'text':'2026.02.21(토)\n2026년 02월 12일\n시험 관리 위원회',
         'sources':[{'id':'s1', 'text':'2026.02.21(토)', 'kind':'cell', 'bbox':[10,100,200,140]},
                    {'id':'s2', 'text':'2026년 02월 12일\n시험 관리 위원회', 'kind':'cell', 'bbox':[10,470,300,540]}]}
    result = ex.explicit_issue_dates(p, {'type':'date'}, 'doc')
    assert len(result) == 1
    assert result[0]['value'] == '2026-02-12'
    assert result[0]['evidence'][0]['source_id'] == 's2'
    p['sources'][1]['text'] = '2026년 02월\n시험 관리 위원회'
    assert ex.explicit_issue_dates(p, {'type':'date'}, 'doc') == []


def test_retry_only_failed_fields(tmp_path, monkeypatch):
    pdf = tmp_path/'x.pdf'; pdf.write_bytes(b'fixture')
    monkeypatch.setattr(ex, 'extract_pdf', lambda _: {'status': 'extracted', 'pages': [
        {'number': 1, 'text': '성명 홍길동', 'sources': [{'id':'p1s1', 'text':'성명 홍길동', 'kind':'line', 'bbox':None}]}]})
    requests = []
    def client(messages):
        p = json.loads(messages[-1]['content']); requests.append(p)
        result = {k: {'value': None, 'evidence_ids': []} for k in p['requested_fields']}
        if 'subject_name' in result:
            result['subject_name'] = {'value':'홍길동', 'evidence_ids':['bad' if not p.get('retry') else 'p1s1']}
        return json.dumps(result)
    result = ex.extract_application(pdf, 'postponement.illness', client=client)
    retries = [r for r in requests if r.get('retry')]
    assert len(retries) == 1
    assert len(requests) == 2
    assert list(retries[0]['requested_fields']) == ['subject_name']
    assert result['fields']['subject_name']['value'] == '홍길동'


def test_real_forms_layout_preserves_cells_and_separates_watermark():
    root = Path(__file__).resolve().parents[2]/'frontend/public/pdfs'
    medical = extract_pdf(root/'홍길동.pdf')['pages'][0]
    opinion = next(s for s in medical['sources'] if '약 8주' in s['text'])
    assert '치료에 대한 소견' not in opinion['text']
    assert '치료' in opinion['label']
    assert any(s['text'] == '홍길동' and '성명' in s['label'] for s in medical['sources'])
    exam = extract_pdf(root/'홍진호.pdf')['pages'][0]
    assert any('020202-3222222' in s['text'] for s in exam['sources'])
    assert any(s['kind'] == 'rotated_text' and 'SAMPLE' in s['text'] for s in exam['sources'])
    issues = ex.consistency_issues({'pages':[medical]}, {'diagnosis':{'value':'우측 무릎 염좌'}})
    assert issues[0]['id'] == 'diagnosis_narrative_difference'


def test_compact_full_page_has_no_missing_sources():
    root = Path(__file__).resolve().parents[2]/'frontend/public/pdfs'
    for name, kind in [('홍길동.pdf','postponement.illness'), ('홍진호.pdf','postponement.exam')]:
        requests = []
        def client(messages):
            assert sum(len(m['content'].encode()) for m in messages) <= ex.MAX_INPUT_BYTES
            data = json.loads(messages[-1]['content']); requests.append(data)
            return json.dumps({k:{'value':None,'evidence_ids':[]} for k in data['requested_fields']})
        result = ex.extract_application(root/name, kind, client=client)
        assert len(requests) == 1
        assert {s['id'] for s in requests[0]['sources']} == {s['id'] for s in result['pdf']['pages'][0]['sources']}
        assert 'issued_on' not in requests[0]['requested_fields']
        assert 'issued_on' not in result['fields']
