"""Build daily-log entries from successful business requests and narrow snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re

from sqlalchemy import select

from user.app.models.annual_status import AnnualStatus
from user.app.models.education import Education
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.models.prosecution_document import ProsecutionDocument
from user.app.models.training_schedule import TrainingSchedule
from user.app.models.training_recalculation import TrainingStatusPolicy, TrainingYearResult
from user.app.models.transfer_intake import TransferIntake
from user.app.services.auth import resolve_session
from user.app.worklog.classification import postponement_label


@dataclass(frozen=True)
class Operation:
    category: str
    action: str
    label: str
    params: dict


_ROUTES = [
    ('POST', r'/(?:persons|reservists)', 'personnel', 'create', '인원 등록'),
    ('PATCH', r'/(?:persons|reservists)/(?P<person>[^/]+)(?:/profile)?', 'personnel', 'update', '인원 정보 수정'),
    ('DELETE', r'/(?:persons|reservists)/(?P<person>[^/]+)', 'personnel', 'delete', '인원 삭제'),
    ('PATCH', r'/persons/(?P<person>[^/]+)/annual-status/(?P<year>\d+)', 'personnel', 'annual_status', '연차별 동원 상태 변경'),
    ('POST', r'/transfers', 'transfer_in', 'submit', '전입 접수'),
    ('PATCH', r'/transfers/(?P<id>\d+)/confirm', 'transfer_in', 'confirm', '전입 승인'),
    ('PATCH', r'/transfers/(?P<id>\d+)/reject', 'transfer_in', 'reject', '전입 반려'),
    ('POST', r'/postponements', 'postponement', 'submit', '보류·연기 신청 등록'),
    ('PATCH', r'/postponements/(?P<id>\d+)', 'postponement', 'update', '보류·연기 신청 수정'),
    ('PATCH', r'/postponements/(?P<id>\d+)/approve', 'postponement', 'approve', '보류·연기 승인'),
    ('PATCH', r'/postponements/(?P<id>\d+)/reject', 'postponement', 'reject', '보류·연기 반려'),
    ('PATCH', r'/postponements/(?P<id>\d+)/revoke', 'postponement', 'revoke', '보류·연기 승인 취소'),
    ('PATCH', r'/postponements/(?P<id>\d+)/resolve', 'postponement', 'resolve', '보류 해소 신고'),
    ('POST', r'/prosecution-documents', 'prosecution', 'create', '고발장 저장'),
    ('PUT', r'/prosecution-documents/(?P<id>[^/]+)', 'prosecution', 'update', '고발장 수정 저장'),
    ('POST', r'/squads/(?P<id>\d+)/fill-positions', 'assignment', 'fill', '분대 편성'),
    ('POST', r'/squads/assignments/confirm', 'assignment', 'confirm', '인원 편성'),
    ('POST', r'/squads/assignments/reset', 'assignment', 'reset', '전체 편성 해제'),
    ('POST', r'/squads/assignments/auto', 'assignment', 'auto', '전체 자동 편성'),
    ('POST', r'/organization/(?P<id>\d+)/release-members', 'assignment', 'release', '편성 해제'),
    ('POST', r'/organization/(?P<id>\d+)/auto-fill', 'assignment', 'auto_fill', '빈자리 자동 편성'),
    ('POST', r'/copilot/apply', 'assignment', 'copilot_apply', '챗봇 제안 실행'),
    ('POST', r'/copilot/undo/(?P<id>[^/]+)', 'assignment', 'copilot_undo', '챗봇 편성 변경 되돌리기'),
    ('POST', r'/organization', 'organization', 'create', '편제 추가'),
    ('PATCH', r'/organization/(?P<id>\d+)/name', 'organization', 'rename', '편제 이름 변경'),
    ('PATCH', r'/organization/(?P<id>\d+)/parent', 'organization', 'move', '상위 편제 변경'),
    ('DELETE', r'/organization/(?P<id>\d+)', 'organization', 'delete', '편제 삭제'),
    ('POST', r'/organization/(?P<id>\d+)/expand', 'organization', 'expand', '편제 확장'),
    ('POST', r'/(?:persons|reservists)/(?P<person>[^/]+)/training-hours', 'training', 'record_create', '훈련 기록 등록'),
    ('PATCH', r'/(?:persons|reservists)/(?P<person>[^/]+)/training-hours/(?P<id>\d+)', 'training', 'record_update', '훈련 기록 수정'),
    ('DELETE', r'/(?:persons|reservists)/(?P<person>[^/]+)/training-hours/(?P<id>\d+)', 'training', 'record_delete', '훈련 기록 삭제'),
    ('POST', r'/reservists/training-schedules', 'training', 'schedule_create', '훈련 일정 등록'),
    ('PUT', r'/reservists/training-schedules/(?P<id>\d+)', 'training', 'schedule_update', '훈련 일정 수정'),
    ('DELETE', r'/reservists/training-schedules/(?P<id>\d+)', 'training', 'schedule_delete', '훈련 일정 삭제'),
    ('POST', r'/reservists/training-schedules/(?P<id>\d+)/move', 'training', 'schedule_move', '훈련 일정 이동'),
    ('POST', r'/reservists/training-schedules/(?P<id>\d+)/cancel', 'training', 'schedule_cancel', '훈련 일정 취소'),
    ('POST', r'/reservists/training-schedules/(?P<id>\d+)/complete', 'training', 'schedule_complete', '훈련 일정 완료'),
    ('POST', r'/reservists/training-schedules/(?P<id>\d+)/roster', 'training', 'roster', '훈련 인원 배정'),
    ('POST', r'/reservists/training-results/bulk-confirm', 'training', 'results', '훈련 결과 확정'),
    ('POST', r'/reservists/training/recalculate/(?P<person>[^/]+)', 'training', 'recalculate', '훈련 시간 재계산'),
    ('POST', r'/reservists/training/recalculate-all', 'training', 'recalculate_all', '전체 훈련 시간 재계산'),
    ('PATCH', r'/reservists/training/status-policies/(?P<id>[^/]+)', 'training', 'policy', '훈련 상태 기준 변경'),
    ('POST', r'/classifier-api/submissions', 'postponement', 'document_submit', '보류·연기 서류 제출'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/cancel', 'postponement', 'analysis_cancel', '서류 분석 취소'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/(?:retry|reanalyze)', 'postponement', 'analysis_retry', '서류 재분석 요청'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/decision', 'postponement', 'document_decision', '제출 서류 처리'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/request-confirmation', 'postponement', 'confirmation', '추가 확인 요청'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/identity', 'postponement', 'document_identity', '제출 서류 대상자 연결'),
    ('POST', r'/classifier-api/submissions/(?P<id>[^/]+)/verify', 'postponement', 'document_verify', '제출 서류 재검증'),
]


def match_operation(method: str, path: str) -> Operation | None:
    for verb, pattern, category, action, label in _ROUTES:
        match = re.fullmatch(pattern, path.rstrip('/')) if method == verb else None
        if match:
            return Operation(category, action, label, match.groupdict())
    return None


PERSON_FIELDS = ('military_number', 'name', 'branch', 'rank', 'unit', 'squad_id', 'position')
PERSON_STATE = PERSON_FIELDS + ('specialty', 'origin_type', 'service_year', 'status', 'mobilization_status',
                                 'discharge_date', 'callup_release_date', 'registration_type')
LABELS = {
    'military_number': '군번', 'name': '성명', 'branch': '군별', 'rank': '계급', 'unit': '소속 부대',
    'squad_id': '편성 분대', 'position': '직책', 'specialty': '주특기', 'service_year': '연차',
    'status': '상태', 'mobilization_status': '동원 상태', 'discharge_date': '전역일',
    'callup_release_date': '소집 해제일', 'registration_type': '등록 구분', 'semester_completed': '학기 이수',
    'type': '신청 구분', 'reason': '사유', 'category': '신청 유형', 'start_date': '시작일', 'end_date': '종료일',
    'credited_hours': '인정 시간', 'source_file': '제출 서류', 'title': '훈련명', 'training_type': '훈련 종류',
    'training_round': '훈련 차수', 'training_year': '훈련 연도', 'education_year': '훈련 연차',
    'scheduled_date': '훈련 날짜', 'attendance_status': '참석 상태', 'training_hours': '이수 시간',
    'sessions': '훈련 일정', 'parent_id': '상위 편제', 'kind': '편제 구분', 'planned_strength': '계획 인원',
    'version': '저장 버전', 'number': '문서번호', 'filename': '제출 서류', 'reason_category': '신청 사유',
    'analysis_state': '분석 상태', 'note': '비고', 'confirmation_requested': '추가 확인 요청',
    'required_hours': '필요 시간', 'counted_hours': '이수 시간', 'unmet_hours': '잔여 시간',
    'carryover_status': '이월 상태', 'needs_review_reason': '검토 사유', 'counts_hours': '이수 시간 합산',
    'credits_hours': '시간 인정', 'advances_round': '차수 진행', 'confirmed_absence': '불참 확정',
    'enabled': '사용 여부', 'prosecution_kind': '고발 구분',
    'applicant_name': '신청자 성명', 'verification_result': '검증 결과', 'application_type': '신청 유형',
    'origin_type': '출신 구분', 'notes': '훈련 비고',
}


def _values(row, fields):
    result = {}
    for field in fields:
        value = getattr(row, field, None)
        result[field] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return result


def _identifiers(value, singular=('person_id', 'military_number'), plural=('person_ids', 'military_numbers')):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in singular and isinstance(item, (str, int)) and str(item):
                found.add(str(item))
            elif key in plural and isinstance(item, list):
                found.update(str(number) for number in item if isinstance(number, (str, int)))
            elif isinstance(item, (list, dict)):
                found.update(_identifiers(item, singular, plural))
    elif isinstance(value, list):
        for item in value:
            found.update(_identifiers(item, singular, plural))
    return found


def capture_state(session_factory, operation, payload, response=None, authorization=''):
    """Read only fields needed for the daily record; never retain request bodies."""
    category, action, params = operation.category, operation.action, operation.params
    response = response if isinstance(response, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    identifier = params.get('id') or response.get('id') or payload.get('id')
    numbers = _identifiers(payload) | _identifiers(response)
    if params.get('person'):
        numbers.add(params['person'])
    state = {'people': {}, 'entities': {}, 'actor': '미인증 요청', 'decision_submission_id': None}
    with session_factory() as db:
        if authorization.lower().startswith('bearer '):
            user = resolve_session(db, authorization[7:])
            if user:
                state['actor'] = user.username
        entities = state['entities']
        if category == 'transfer_in':
            rows = db.scalars(select(TransferIntake).where(TransferIntake.id == identifier)).all() if identifier else []
            for row in rows:
                value = _values(row, ('military_number', 'status'))
                value.update({key: row.person_details.get(key) for key in PERSON_FIELDS})
                entities[f'전입 {row.id}'] = value
                numbers.add(row.military_number)
                state['people'][row.military_number] = {key: value.get(key) for key in PERSON_FIELDS}
        elif category == 'prosecution':
            row = db.get(ProsecutionDocument, str(identifier)) if identifier else None
            if row:
                fields = json.loads(row.fields_json)
                entities[f'고발장 {row.id}'] = {'version': row.version, 'number': fields.get('number', '')}
                numbers.add(row.person_id)
        elif category == 'organization':
            for row in db.scalars(select(OrganizationNode)).all():
                entities[f'편제 {row.id}'] = _values(row, ('name', 'kind', 'parent_id', 'squad_id', 'planned_strength'))
        elif category == 'postponement':
            if action.startswith(('document_', 'analysis_')) or action == 'confirmation':
                from classifier_agent import submissions
                try:
                    item = submissions.get(identifier) if identifier else None
                except KeyError:
                    item = None
                if item:
                    fields = ('filename', 'reason_category', 'application_type', 'status', 'analysis_state', 'note',
                              'confirmation_requested', 'analysis_run', 'decided_at', 'military_number', 'applicant_name')
                    entities[f'제출 {identifier}'] = {field: item.get(field) for field in fields}
                    if action == 'document_verify':
                        verification = item.get('verification') or {}
                        entities[f'제출 {identifier}']['verification_result'] = verification.get('result_label') or verification.get('result')
                        entities[f'제출 {identifier}']['review_revision'] = item.get('review_revision')
                    number = item.get('military_number') or ''
                    state['people'][number or f'submission:{identifier}'] = {
                        'military_number': number, 'name': item.get('applicant_name', ''),
                    }
                    if number:
                        numbers.add(number)
            else:
                query = select(Postponement)
                if identifier:
                    query = query.where(Postponement.id == identifier)
                elif payload.get('classifier_submission_id'):
                    query = query.where(Postponement.classifier_submission_id == payload['classifier_submission_id'])
                else:
                    query = query.where(False)
                for row in db.scalars(query).all():
                    entities[f'신청 {row.id}'] = _values(row, ('person_id', 'type', 'reason', 'category', 'status',
                        'start_date', 'end_date', 'credited_hours', 'source_file', 'resolution_reported_at'))
                    numbers.add(row.person_id)
                    if action in ('approve', 'reject'):
                        state['decision_submission_id'] = row.classifier_submission_id
        elif category == 'training':
            if action.startswith('recalculate'):
                query = select(TrainingYearResult)
                if params.get('person'):
                    query = query.where(TrainingYearResult.person_id == params['person'])
                for row in db.scalars(query).all():
                    entities[f'훈련 집계 {row.id}'] = _values(row, ('person_id', 'service_year', 'training_type',
                        'required_hours', 'counted_hours', 'credited_hours', 'unmet_hours', 'carryover_status', 'needs_review_reason'))
                    numbers.add(row.person_id)
            elif action == 'policy':
                row = db.get(TrainingStatusPolicy, identifier)
                if row:
                    entities[f'훈련 기준 {identifier}'] = _values(row, ('counts_hours', 'credits_hours', 'advances_round',
                        'confirmed_absence', 'enabled', 'prosecution_kind'))
            ids = _identifiers(payload, ('education_id',), ()) | _identifiers(response, ('education_id',), ())
            if action in ('record_update', 'record_delete') and identifier:
                ids.add(str(identifier))
            query = select(Education)
            if action.startswith('schedule_') or action == 'roster':
                row = db.get(TrainingSchedule, int(identifier)) if identifier else None
                if row:
                    entities[f'훈련 일정 {row.id}'] = {**_values(row, ('title', 'training_type', 'training_round', 'service_year', 'status')),
                        'sessions': [{'날짜': str(item.session_date), '시간': item.credited_hours} for item in row.sessions]}
                query = query.where(Education.schedule_id == identifier) if identifier else query.where(False)
            elif ids:
                query = query.where(Education.id.in_([int(value) for value in ids if value.isdigit()]))
            elif action == 'record_create' and params.get('person'):
                query = query.where(Education.person_id == params['person'])
            else:
                query = query.where(False)
            for row in db.scalars(query).all():
                entities[f'훈련 기록 {row.id}'] = _values(row, ('person_id', 'education_year', 'training_year', 'training_type',
                    'training_round', 'scheduled_date', 'attendance_status', 'training_hours', 'version', 'notes'))
                numbers.add(row.person_id)
        if action == 'annual_status':
            row = db.get(AnnualStatus, (params['person'], int(params['year'])))
            if row:
                entities[f"{params['year']}년차 상태"] = _values(row, ('mobilization_status', 'semester_completed'))
        people = select(Person) if category == 'assignment' else select(Person).where(Person.military_number.in_(numbers))
        for person in db.scalars(people).all():
            state['people'][person.military_number] = _values(person, PERSON_STATE)
        if category == 'personnel' and action != 'annual_status':
            entities.update({f'인원 {key}': value for key, value in state['people'].items()})
    return state


def build_event(operation, before, after, payload, response):
    category, action, label = operation.category, operation.action, operation.label
    payload = payload if isinstance(payload, dict) else {}
    response = response if isinstance(response, dict) else {}
    previous, current = before['entities'], after['entities']
    people = {**before['people'], **after['people']}
    if action.startswith(('document_', 'analysis_')) or action == 'confirmation':
        people = after['people'] or before['people']
    if category == 'personnel' and operation.params.get('person') != payload.get('military_number') and payload.get('military_number') in after['people']:
        people = {payload['military_number']: after['people'][payload['military_number']]}
    if category == 'assignment':
        changed = {key for key in people if before['people'].get(key) != after['people'].get(key)}
        people = {key: value for key, value in people.items() if key in changed}
        previous = {key: {field: value.get(field) for field in ('squad_id', 'mobilization_status')}
                    for key, value in before['people'].items() if key in changed}
        current = {key: {field: value.get(field) for field in ('squad_id', 'mobilization_status')}
                   for key, value in after['people'].items() if key in changed}
    if previous == current:
        return None
    if category == 'training' and action in ('results', 'record_create', 'record_update', 'record_delete', 'roster', 'recalculate', 'recalculate_all'):
        affected = {value.get('person_id') for key in previous.keys() | current.keys()
                    if previous.get(key) != current.get(key)
                    for value in (previous.get(key, {}), current.get(key, {})) if value.get('person_id')}
        people = {key: value for key, value in people.items() if key in affected}
    changes = []
    ignored = {'analysis_run', 'decided_at', 'person_id', 'military_number', 'resolution_reported_at', 'review_revision'}
    for key in sorted(previous.keys() | current.keys()):
        old, new = previous.get(key, {}), current.get(key, {})
        if old == new:
            continue
        for field in sorted(old.keys() | new.keys()):
            if field not in ignored and old.get(field) != new.get(field):
                changes.append({'대상': key, '항목': LABELS.get(field, field), '이전': old.get(field), '이후': new.get(field)})
    if action == 'document_decision':
        label = '보류·연기 서류 승인' if response.get('status') == 'approved' else '보류·연기 서류 반려'
    names = [person.get('name') or person.get('military_number') for person in people.values()]
    names = [value for value in names if value]
    summary = label + (f' · {names[0]}' + (f' 외 {len(names) - 1}명' if len(names) > 1 else '') if names else '')
    dedupe = None
    if category == 'prosecution':
        dedupe = f"prosecution:{response.get('id')}:{response.get('version')}"
    elif action == 'results':
        dedupe = f"training-results:{payload.get('idempotency_key')}"
    elif action == 'document_submit':
        dedupe = f"submission:{response.get('id')}"
    elif action == 'document_decision':
        dedupe = f"submission-decision:{response.get('id')}:{response.get('status')}"
    details = {'처리 내용': label, '변경 항목': changes}
    if category == 'postponement':
        for entity in (current or previous).values():
            kind = postponement_label(entity.get('type') or entity.get('application_type') or entity.get('category'))
            if kind:
                details['신청 구분'] = kind
                break
    return {'category': category, 'action': f'{category}.{action}', 'summary': summary,
            'actor': before['actor'], 'people': [{key: person.get(key) for key in PERSON_FIELDS} for person in people.values()],
            'details': details, 'dedupe_key': dedupe}
