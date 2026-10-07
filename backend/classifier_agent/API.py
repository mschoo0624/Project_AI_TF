"""Stage 1/2 extraction and stage 3 verification; independent of approval writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .extraction import ModelError, catalog, extract_application, selected_fields
from .verification import BASE, rules_catalog, verify_application
from . import submissions

app = FastAPI(title='Qwen PDF extraction', version='1.0')
busy = BoundedSemaphore(1)


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
    return submissions.list_all()


def stored(id):
    try: return submissions.get(id)
    except KeyError as exc: raise HTTPException(404, '제출 건을 찾을 수 없습니다.') from exc


@app.get('/submissions/{id}')
def submission_detail(id: str):
    return stored(id)


@app.get('/submissions/{id}/pdf')
def submission_pdf(id: str):
    item = stored(id)
    path = submissions.root() / (item['id'] + '.pdf')
    if not path.is_file(): raise HTTPException(404, '원본 PDF를 찾을 수 없습니다.')
    return FileResponse(path, media_type='application/pdf')


@app.post('/submissions')
def create_submission(application_type: str = Form(...), military_number: str = Form(...),
                      applicant_name: str = Form(...), file: UploadFile = File(...)):
    try: selected_fields(application_type)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    if not military_number.strip() or not applicant_name.strip(): raise HTTPException(422, '대상자 정보가 필요합니다.')
    if not busy.acquire(blocking=False): raise HTTPException(429, '다른 문서를 처리 중입니다.')
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
        extraction = extract_application(path, application_type, applicant_name=applicant_name)
        item = submissions.save({'id': id, 'filename': Path(file.filename or 'document.pdf').name,
            'saved_path': f'/submissions/{id}/pdf', 'military_number': military_number.strip(),
            'applicant_name': applicant_name, 'application_type': application_type,
            'reason_category': catalog()[1][application_type]['label'], 'extraction': extraction,
            'verification': None, 'context': {}, 'status': 'pending', 'note': None,
            'confirmation_requested': False, 'created_at': submissions.now(), 'decided_at': None})
        completed = True
        return item
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except ModelError as exc: raise HTTPException(503, str(exc)) from exc
    finally:
        file.file.close()
        if not completed and path: path.unlink(missing_ok=True)
        busy.release()


class StoredVerification(BaseModel):
    context: dict[str, ContextFact] = Field(default_factory=dict)


@app.post('/submissions/{id}/verify')
def verify_submission(id: str, payload: StoredVerification):
    item = stored(id)
    context = {k: v.model_dump() for k, v in payload.context.items()}
    if context.get('applicant_service_number', {}).get('value') != item['military_number']:
        raise HTTPException(422, '제출 대상자와 검증 대상자가 다릅니다.')
    result = verify_application([item['extraction']], context)
    def mutate(current):
        if current['status'] != 'pending': raise HTTPException(409, '처리된 신청은 다시 검증할 수 없습니다.')
        current.update(verification=result, context=context)
    submissions.update(id, mutate)
    return result


class DecisionRequest(BaseModel):
    decision: Literal['approved', 'declined']
    note: str | None = Field(default=None, max_length=2000)


@app.post('/submissions/{id}/decision')
def submission_decision(id: str, payload: DecisionRequest):
    stored(id)
    def mutate(current):
        if current['status'] == payload.decision: return
        if current['status'] != 'pending': raise HTTPException(409, '이미 처리된 신청입니다.')
        current.update(status=payload.decision, decided_at=submissions.now(), note=payload.note, confirmation_requested=False)
    return submissions.update(id, mutate)


class ConfirmationRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


@app.post('/submissions/{id}/request-confirmation')
def request_confirmation(id: str, payload: ConfirmationRequest):
    stored(id)
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
