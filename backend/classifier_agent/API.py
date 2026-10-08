"""Stage 1/2 extraction and stage 3 verification; independent of approval writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from uuid import uuid4
from typing import Literal
from concurrent.futures import ThreadPoolExecutor, CancelledError
from contextlib import asynccontextmanager
from io import BytesIO
import logging
import pdfplumber
import os
import httpx

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from .extraction import ModelError, catalog, extract_application, selected_fields
from .verification import BASE, rules_catalog, verify_application
from . import submissions

@asynccontextmanager
async def lifespan(app):
    for item in submissions.list_all():
        if item.get('analysis_state') in ('queued', 'analyzing'):
            submissions.update(item['id'], lambda row: row.update(analysis_state='failed', analysis_error='서버가 재시작되었습니다. 다시 분석해 주세요.'))
    try:
        yield
    finally:
        for item in submissions.list_all():
            if item.get('analysis_state') in ('queued', 'analyzing'):
                submissions.update(item['id'], lambda row: row.update(analysis_state='failed', analysis_error='서버가 종료되어 분석이 중단되었습니다. 다시 분석해 주세요.'))


app = FastAPI(title='Qwen PDF extraction', version='1.0', lifespan=lifespan)
busy = BoundedSemaphore(1)
render_busy = BoundedSemaphore(1)
jobs = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pdf-analysis')


def review_item(item):
    entry = rules_catalog()['types'][item['application_type']]
    item['review_items'] = entry.get('review_items', [])
    item.setdefault('analysis_state', 'completed')
    item.setdefault('review_revision', 0)
    if item.get('review_rules_version') != rules_catalog()['version']:
        item['review_checks'] = {}
    item.setdefault('review_checks', {})
    return item


def require_complete(item):
    if item.get('analysis_state', 'completed') != 'completed':
        raise HTTPException(409, '분석 완료된 문서만 검토할 수 있습니다.')


def analyze_submission(id):
    with busy:
        if stored(id)['analysis_state'] != 'queued': return
        run_id = None
        def start(row):
            if row.get('analysis_state') != 'queued': raise CancelledError()
            row.update(analysis_state='analyzing', analysis_error=None)
        try:
            item = submissions.update(id, start)
            run_id = item.get('analysis_run')
            def cancelled():
                current = stored(id)
                return current['analysis_state'] != 'analyzing' or current.get('analysis_run') != run_id
            extraction = extract_application(submissions.root()/(id+'.pdf'), item['application_type'],
                applicant_name=item['applicant_name'] or None,
                cancelled=cancelled)
            verification = verify_application([extraction], {})
            def finish(row):
                if row.get('analysis_state') != 'analyzing' or row.get('analysis_run') != run_id: return
                field = extraction.get('fields', {}).get('subject_name', {})
                name = field.get('value') if field.get('status') == 'observed' else None
                row.update(extraction=extraction, verification=verification, analysis_state='completed',
                           analysis_completed_at=submissions.now(), review_checks={}, review_revision=row.get('review_revision', 0)+1)
                if not row.get('applicant_name') and isinstance(name, str): row['applicant_name'] = name
            finished = submissions.update(id, finish)
            if finished.get('analysis_state') == 'completed' and finished['status'] == 'pending' and finished.get('analysis_run') == run_id:
                try:
                    base = os.getenv('BUSINESS_API_URL', 'http://127.0.0.1:8002').rstrip('/')
                    response = httpx.post(base+'/postponements/resolve-applicant', json={'submission_id': id}, timeout=15)
                    response.raise_for_status()
                    linked = response.json()['submission']
                    if linked.get('military_number'):
                        response = httpx.post(base+'/postponements/verify', json={
                            'person_id': linked['military_number'], 'submission_id': id,
                            'documents': [extraction], 'context': {}}, timeout=30)
                        response.raise_for_status()
                except httpx.HTTPError:
                    logging.getLogger(__name__).warning('Automatic applicant linking unavailable for %s; manual linking remains available', id)
        except CancelledError:
            pass
        except Exception:
            logging.getLogger(__name__).exception('PDF analysis failed: %s', id)
            def fail(row):
                if row.get('analysis_state') in ('queued', 'analyzing') and row.get('analysis_run') == run_id:
                    row.update(analysis_state='failed', analysis_error='PDF 분석에 실패했습니다. 파일과 분석 서버를 확인한 뒤 다시 시도하세요.')
            submissions.update(id, fail)


class ContextFact(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    value: str | bool | int | None
    source: str = Field(min_length=1, max_length=1000)


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    documents: list[dict] = Field(min_length=1, max_length=20)
    context: dict[str, ContextFact] = Field(default_factory=dict)


@app.get('/verification-rules')
def verification_rules():
    return rules_catalog()


@app.get('/verification-sources/{table}')
def verification_source(table: int):
    if table not in (5, 6, 7):
        raise HTTPException(404, '존재하지 않는 기준표입니다.')
    entries = rules_catalog()['types'].values()
    source = next(e['citation'] for e in entries if e['citation']['table'] == table)
    return FileResponse(BASE/source['path'], media_type='application/pdf')


@app.post('/verify')
def verify(payload: VerificationRequest):
    try:
        return verify_application(payload.documents, {k: v.model_dump() for k, v in payload.context.items()})
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(422, '검증 입력을 확인하세요: ' + str(exc)) from exc


@app.get('/application-types')
def application_types():
    return list(catalog()[1].values())


@app.get('/field-definitions')
def field_definitions():
    return catalog()[0]['fields']


@app.get('/submissions')
def submission_list():
    return [review_item(item) for item in submissions.list_all() if not item.get('archived')]


def stored(id):
    try: return review_item(submissions.get(id))
    except KeyError as exc: raise HTTPException(404, '제출 건을 찾을 수 없습니다.') from exc


@app.get('/submissions/{id}')
def submission_detail(id: str):
    return stored(id)


@app.get('/submissions/{id}/pdf')
def submission_pdf(id: str, download: bool = False):
    item = stored(id)
    path = submissions.root() / (item['id'] + '.pdf')
    if not path.is_file(): raise HTTPException(404, '원본 PDF를 찾을 수 없습니다.')
    return FileResponse(path, media_type='application/pdf', filename=item['filename'] if download else None,
                        content_disposition_type='attachment' if download else 'inline')


@app.post('/submissions', status_code=202)
def create_submission(application_type: str = Form(...), military_number: str = Form(''),
                      applicant_name: str = Form(''), file: UploadFile = File(...)):
    try: selected_fields(application_type)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    id = 'qwen_' + uuid4().hex
    path = None
    completed = False
    try:
        path = submissions.root() / (id + '.pdf')
        size = 0
        with path.open('xb') as stream:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 20 * 1024 * 1024: raise HTTPException(413, 'PDF는 20MB 이하만 지원합니다.')
                stream.write(chunk)
        item = submissions.save({'id': id, 'filename': Path(file.filename or 'document.pdf').name,
            'saved_path': f'/submissions/{id}/pdf', 'military_number': military_number.strip(),
            'applicant_name': applicant_name, 'application_type': application_type,
            'reason_category': catalog()[1][application_type]['label'], 'extraction': {'fields': {}, 'application_type': application_type},
            'analysis_state': 'queued', 'analysis_error': None, 'review_checks': {}, 'review_revision': 0,
            'verification': None, 'context': {}, 'status': 'pending', 'note': None,
            'confirmation_requested': False, 'created_at': submissions.now(), 'decided_at': None})
        completed = True
        jobs.submit(analyze_submission, id)
        return review_item(item)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except ModelError as exc: raise HTTPException(503, str(exc)) from exc
    finally:
        file.file.close()
        if not completed and path: path.unlink(missing_ok=True)


@app.post('/submissions/{id}/cancel')
def cancel_submission(id: str):
    stored(id)
    def cancel(row):
        if row.get('analysis_state') not in ('queued', 'analyzing'):
            raise HTTPException(409, '현재 분석 중인 문서만 취소할 수 있습니다.')
        row.update(analysis_state='cancelled', cancelled_at=submissions.now())
    return review_item(submissions.update(id, cancel))


@app.post('/submissions/{id}/retry')
def retry_submission(id: str):
    stored(id)
    def retry(row):
        if row.get('analysis_state') != 'failed' and not (row.get('reanalysis') and row.get('analysis_state') == 'cancelled'):
            raise HTTPException(409, '실패하거나 취소된 재검토만 다시 시도할 수 있습니다.')
        row.update(analysis_state='queued', analysis_run=uuid4().hex, analysis_error=None, review_checks={}, review_revision=row.get('review_revision', 0)+1)
    item = submissions.update(id, retry)
    jobs.submit(analyze_submission, id)
    return review_item(item)


@app.post('/submissions/{id}/reanalyze', status_code=202)
def reanalyze_submission(id: str):
    stored(id)
    def restart(row):
        require_complete(row)
        if row.get('archived'): raise HTTPException(409, '보관 처리된 문서는 재검토할 수 없습니다.')
        row.update(analysis_state='queued', analysis_run=uuid4().hex, reanalysis=True,
                   analysis_error=None, review_checks={}, review_revision=row.get('review_revision', 0)+1)
    item = submissions.update(id, restart)
    jobs.submit(analyze_submission, id)
    return review_item(item)


@app.get('/submissions/{id}/pages/{page}/image')
def page_image(id: str, page: int):
    stored(id)
    with render_busy, pdfplumber.open(submissions.root()/(id+'.pdf')) as pdf:
        if page < 1 or page > len(pdf.pages): raise HTTPException(404, '해당 페이지가 없습니다.')
        image = pdf.pages[page-1].to_image(resolution=110).original
        output = BytesIO(); image.save(output, format='PNG')
    return Response(output.getvalue(), media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


class ReviewChecks(BaseModel):
    checks: dict[str, bool]
    revision: int


@app.patch('/submissions/{id}/review-checks')
def save_review_checks(id: str, payload: ReviewChecks):
    item = stored(id); require_complete(item)
    allowed = {entry['id'] for entry in item['review_items']}
    if not payload.checks.keys() <= allowed: raise HTTPException(422, '알 수 없는 검토 항목입니다.')
    def update(row):
        require_complete(row)
        if row['status'] != 'pending' or row.get('review_revision', 0) != payload.revision:
            raise HTTPException(409, '검토 기록이 변경되었습니다. 새로고침 후 다시 확인하세요.')
        row.update(review_checks=payload.checks, review_revision=payload.revision+1,
                   review_rules_version=rules_catalog()['version'], reviewed_at=submissions.now())
    return review_item(submissions.update(id, update))


class StoredVerification(BaseModel):
    context: dict[str, ContextFact] = Field(default_factory=dict)


class IdentityRequest(BaseModel):
    military_number: str = Field(min_length=1)
    applicant_name: str = Field(min_length=1)


@app.post('/submissions/{id}/identity')
def set_identity(id: str, payload: IdentityRequest):
    require_complete(stored(id))
    def mutate(current):
        if current['status'] != 'pending' or current.get('military_number'):
            raise HTTPException(409, '이미 연결되거나 처리된 신청입니다.')
        current.update(military_number=payload.military_number, applicant_name=payload.applicant_name,
                       verification=None, context={}, review_checks={}, review_revision=current.get('review_revision', 0)+1)
    return submissions.update(id, mutate)


@app.post('/submissions/{id}/verify')
def verify_submission(id: str, payload: StoredVerification):
    item = stored(id)
    require_complete(item)
    context = {k: v.model_dump() for k, v in payload.context.items()}
    if context.get('applicant_service_number', {}).get('value', '') != item['military_number']:
        raise HTTPException(422, '제출 대상자와 검증 대상자가 다릅니다.')
    result = verify_application([item['extraction']], context)
    def mutate(current):
        if current['status'] != 'pending': raise HTTPException(409, '처리된 신청은 다시 검증할 수 없습니다.')
        current.update(verification=result, context=context, review_checks={}, review_revision=current.get('review_revision', 0)+1)
    submissions.update(id, mutate)
    return result


class DecisionRequest(BaseModel):
    decision: Literal['approved', 'declined']
    note: str | None = Field(default=None, max_length=2000)


@app.post('/submissions/{id}/decision')
def submission_decision(id: str, payload: DecisionRequest):
    require_complete(stored(id))
    def mutate(current):
        if payload.decision == 'approved' and not current.get('military_number'):
            raise HTTPException(422, '먼저 대상자를 연결하세요.')
        if current['status'] == payload.decision: return
        if current['status'] != 'pending': raise HTTPException(409, '이미 처리된 신청입니다.')
        require_complete(current)
        if payload.decision == 'approved':
            current = review_item(current)
            checks = current['review_checks']
            if not current['review_items'] or not all(checks.get(check['id']) is True for check in current['review_items']):
                raise HTTPException(409, '모든 근거 항목을 확인해야 최종 승인할 수 있습니다.')
        current.update(status=payload.decision, decided_at=submissions.now(), note=payload.note, confirmation_requested=False)
    return submissions.update(id, mutate)


class ConfirmationRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


@app.post('/submissions/{id}/request-confirmation')
def request_confirmation(id: str, payload: ConfirmationRequest):
    require_complete(stored(id))
    def mutate(current):
        if current['status'] != 'pending': raise HTTPException(409, '이미 처리된 신청입니다.')
        current.update(confirmation_requested=True, note=payload.note)
    return submissions.update(id, mutate)


@app.post('/extract-pdf')
def extract_pdf_endpoint(application_type: str = Form(...), file: UploadFile = File(...),
                         applicant_name: str | None = Form(None)):
    try:
        selected_fields(application_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not busy.acquire(blocking=False):
        raise HTTPException(429, '다른 문서를 처리 중입니다. 잠시 후 다시 시도하세요.')
    try:
        with TemporaryDirectory(prefix='qwen-pdf-') as folder:
            path = Path(folder) / 'document.pdf'
            size = 0
            with path.open('wb') as stream:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        raise HTTPException(413, 'PDF는 20MB 이하만 지원합니다.')
                    stream.write(chunk)
            return extract_application(path, application_type, applicant_name=applicant_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        file.file.close()
        busy.release()
