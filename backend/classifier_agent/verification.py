"""Deterministic, evidence-aware stage 3. Never writes an approval decision."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from .extraction import BASE, catalog, validate_field

RULES = BASE / 'verification_rules.json'
LABELS = {'sufficient': '근거 충족', 'insufficient': '근거 부족',
          'not_met': '요건 불충족', 'review_required': '담당자 검토 필요'}


def rules_catalog():
    return json.loads(RULES.read_text(encoding='utf-8'))


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('정확한 YYYY-MM-DD 날짜가 필요합니다.')
    return date.fromisoformat(value)


def _same(a, b):
    return type(a) is type(b) and a == b


def _aggregate(states, mode='all'):
    if not states:
        return 'review'
    if mode == 'any':
        if 'pass' in states: return 'pass'
        if 'review' in states: return 'review'
        if 'missing' in states: return 'missing'
        return 'fail'
    if 'fail' in states: return 'fail'
    if 'review' in states: return 'review'
    if 'missing' in states: return 'missing'
    return 'pass'


class Evaluation:
    def __init__(self, documents, context):
        self.documents, self.context = documents, context
        self.definitions = catalog()[0]['fields']

    def read(self, key):
        if key.startswith('context.'):
            entry = self.context.get(key[8:])
            if entry is None:
                return None, 'missing', []
            if not isinstance(entry, dict) or not isinstance(entry.get('source'), str) or not entry['source'].strip():
                return None, 'review', []
            value = entry.get('value')
            return value, 'missing' if value is None else 'pass', [entry]
        values, evidence, invalid = [], [], False
        spec = self.definitions.get(key)
        if not spec:
            return None, 'review', []
        for doc in self.documents:
            field = doc.get('fields', {}).get(key)
            if not field:
                continue
            if field.get('status') in ('invalid', 'conflicting', 'unresolved') or field.get('errors'):
                invalid = True
                evidence.extend(field.get('evidence', []))
                continue
            value = field.get('value')
            if value is None:
                continue
            quotes = field.get('evidence', [])
            valid = bool(quotes)
            for quote in quotes:
                if not isinstance(quote, dict):
                    valid = False; continue
                page = next((p for p in doc.get('pdf', {}).get('pages', []) if p['number'] == quote.get('page')), None)
                if page is None or quote.get('document_id') != doc.get('document_id'):
                    valid = False; continue
                checked = validate_field({'value': value, 'evidence': [quote.get('quote')]}, spec, page, doc['document_id'])
                if checked['errors']: valid = False
            if not valid:
                invalid = True
            else:
                if not any(_same(value, v) for v in values): values.append(value)
                evidence.extend(quotes)
        if invalid or len(values) > 1:
            return None, 'review', evidence
        return (values[0], 'pass', evidence) if values else (None, 'missing', evidence)

    def evaluate(self, rule):
        op = rule['op']
        result = {'id': rule['id'], 'label': rule['label'], 'status': 'review',
                  'required_fields': rule.get('fields', []), 'evidence': [], 'values': {},
                  'message': rule.get('message', rule['label'])}
        if op in ('all', 'any'):
            result['children'] = [self.evaluate(r) for r in rule['children']]
            result['status'] = _aggregate([r['status'] for r in result['children']], op)
            result['operator'] = op
            if op == 'any' and result['status'] == 'pass':
                for child in result['children']:
                    child['required_for_result'] = child['status'] == 'pass'
            return result
        if op == 'manual':
            for key in rule.get('fields', []):
                value, _, proof = self.read(key)
                result['values'][key] = value; result['evidence'].extend(proof)
            return result
        states = []
        for key in rule['fields']:
            value, state, proof = self.read(key)
            result['values'][key] = value; states.append(state); result['evidence'].extend(proof)
        state = _aggregate(states)
        if state != 'pass':
            result['status'] = state
            return result
        values = list(result['values'].values())
        try:
            passed = None
            if op == 'present': passed = True
            elif op == 'equal_fields': passed = _same(values[0], values[1])
            elif op == 'equals':
                if type(values[0]) is type(rule['value']): passed = values[0] == rule['value']
            elif op == 'enum':
                if any(_same(values[0], v) for v in rule['accepted']): passed = True
                elif any(_same(values[0], v) for v in rule.get('rejected', [])): passed = False
                # Unrecognised wording is not a proven negative.
            elif op == 'less_than':
                if type(values[0]) is int and values[0] >= 0: passed = values[0] < rule['limit']
            elif op == 'days_at_least':
                match = re.fullmatch(r'\s*(\d+)\s*일(?:간)?\s*', str(values[0]))
                if match: passed = int(match[1]) >= rule['days']
            elif op == 'overlap':
                start, end, train_start, train_end = map(_date, values)
                if start > end or train_start > train_end: raise ValueError()
                passed = start <= train_end and train_start <= end
            elif op == 'window':
                day, start, end = map(_date, values)
                if start > end: raise ValueError()
                passed = day + timedelta(days=rule['after']) >= start and day - timedelta(days=rule['before']) <= end
            elif op == 'not_after': passed = _date(values[0]) <= _date(values[1])
            elif op == 'point_window': passed = abs((_date(values[0]) - _date(values[1])).days) <= rule['days']
            elif op == 'year_age':
                birth, assessment = map(_date, values)
                if birth > assessment: raise ValueError()
                passed = assessment.year - birth.year >= rule['years']
            result['status'] = 'review' if passed is None else 'pass' if passed else 'fail'
        except (ValueError, TypeError, OverflowError):
            result['status'] = 'review'
            result['message'] = '값의 형식·기간 순서 또는 단위를 확인해야 합니다.'
        return result


def verify_application(documents, context=None):
    if not documents:
        raise ValueError('추출 결과가 하나 이상 필요합니다.')
    kinds = {d.get('application_type') for d in documents}
    if len(kinds) != 1:
        raise ValueError('한 신청 유형의 문서만 함께 검증할 수 있습니다.')
    kind = kinds.pop()
    config = rules_catalog()
    if kind not in config['types']:
        raise ValueError('알 수 없는 신청 유형입니다.')
    if len({d.get('document_id') for d in documents}) != len(documents):
        raise ValueError('동일 문서가 중복 제출되었습니다.')
    entry = config['types'][kind]
    evaluator = Evaluation(documents, context or {})
    checks = [evaluator.evaluate(r) for r in config['common'] + entry['checks']]
    # A second matching identifier must not conceal an explicit mismatch.
    for field, context_key in [('subject_service_number', 'context.applicant_service_number'),
                               ('subject_birth_date', 'context.applicant_birth_date')]:
        left, ls, _ = evaluator.read(field)
        right, rs, _ = evaluator.read(context_key)
        if ls == rs == 'pass' and not _same(left, right):
            checks.append({'id': 'identity_mismatch', 'label': '본인 식별정보 불일치', 'status': 'fail',
                           'message': '다른 식별항목이 일치해도 명시적 불일치를 무시하지 않습니다.',
                           'required_fields': [field, context_key], 'evidence': []})
    source = entry['citation']
    source_path = (BASE / source['path']).resolve()
    unchanged = source_path.is_file() and hashlib.sha256(source_path.read_bytes()).hexdigest() == source['sha256']
    integrity = 'pass' if unchanged else 'review'
    checks.insert(0, {'id': 'rule_source_integrity', 'label': '기준표 버전 확인', 'status': integrity,
                      'message': '등록된 기준표 SHA-256 대조', 'evidence': [], 'required_fields': []})
    no_readable_evidence = all(d.get('pdf', {}).get('status') == 'no_text' for d in documents)
    if any(d.get('pdf', {}).get('status') != 'extracted' for d in documents):
        checks.append({'id': 'document_completeness', 'label': '제출 문서에서 읽을 수 있는 근거', 'status': 'missing' if no_readable_evidence else 'review',
                       'message': '신청 요건을 뒷받침하는 정보를 읽을 수 없어 근거가 부족합니다.' if no_readable_evidence else '일부 페이지의 누락 여부를 확인해야 합니다.', 'evidence': [], 'required_fields': []})
    state = _aggregate([c['status'] for c in checks])
    if no_readable_evidence: state = 'missing'
    # A changed rule source must never produce a substantive conclusion.
    if not unchanged: state = 'review'
    decision = {'pass': 'sufficient', 'fail': 'not_met', 'missing': 'insufficient', 'review': 'review_required'}[state]
    def leaves(nodes):
        for n in nodes:
            if n['status'] == 'pass': continue
            if 'children' in n: yield from leaves(n['children'])
            else: yield n
    missing = sorted({key for c in leaves(checks) if c['status'] == 'missing'
                      for key in c.get('required_fields', []) if evaluator.read(key)[1] == 'missing'})
    for c in checks:
        c['citation'] = source if c['id'] not in ('identity', 'identity_mismatch', 'document_completeness', 'rule_source_integrity') else None
    return {'schema_version': 1, 'rules_version': config['version'], 'application_type': kind,
            'application_label': entry['label'], 'result': decision, 'result_label': LABELS[decision],
            'checks': checks, 'missing_information': missing, 'related_provisions': [source],
            'coverage': entry['coverage'], 'training_scope': entry['training_scope'],
            'automatic_approval': False, 'authenticity': 'not_checked',
            'basis': '사용자가 제공한 기준표 버전에 대한 신청 근거 검토. 승인/반려 저장 없음.',
            'legal_currency_verified': False}
