from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from user.app.models.user import User
from user.app.services.auth import require_scheduler, require_viewer
from . import repository
from .pdf import template_path


router = APIRouter(prefix='/worklogs', tags=['worklogs'])


class ConfirmWorkLog(BaseModel):
    notes: str = Field(default='', max_length=20000)
    expected_event_id: int = Field(ge=0)


@router.get('/today', dependencies=[Depends(require_viewer)])
def today():
    return repository.ensure_today()


@router.get('/template', dependencies=[Depends(require_viewer)])
def template():
    path = template_path()
    if not path.is_file():
        raise HTTPException(503, '업무일지 양식 파일을 찾을 수 없습니다.')
    return FileResponse(path, media_type='application/pdf', headers={'Cache-Control': 'no-store'})


@router.get('', dependencies=[Depends(require_viewer)])
def list_days():
    return repository.list_days()


@router.get('/{day}', dependencies=[Depends(require_viewer)])
def get_day(day: date):
    result = repository.get_day(day.isoformat())
    if result is None:
        raise HTTPException(404, '업무일지를 찾을 수 없습니다.')
    return result


@router.post('/{day}/confirm')
def confirm(day: date, payload: ConfirmWorkLog, actor: User = Depends(require_scheduler)):
    try:
        label = actor.username if actor.username != 'unauthenticated' else '미인증 요청'
        return repository.confirm(day.isoformat(), notes=payload.notes, expected_event_id=payload.expected_event_id, actor=label)
    except KeyError:
        raise HTTPException(404, '업무일지를 찾을 수 없습니다.') from None
    except repository.ChangedWorkLog as error:
        raise HTTPException(409, str(error)) from None
    except FileNotFoundError:
        raise HTTPException(503, '업무일지 양식 파일을 찾을 수 없습니다. 저장하지 않았습니다.') from None


@router.post('/{day}/preview', dependencies=[Depends(require_viewer)])
def preview(day: date, payload: ConfirmWorkLog):
    try:
        data = repository.preview(day.isoformat(), notes=payload.notes, expected_event_id=payload.expected_event_id)
    except KeyError:
        raise HTTPException(404, '업무일지를 찾을 수 없습니다.') from None
    except repository.ChangedWorkLog as error:
        raise HTTPException(409, str(error)) from None
    except FileNotFoundError:
        raise HTTPException(503, '업무일지 양식 파일을 찾을 수 없습니다.') from None
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': f'inline; filename="worklog-{day.isoformat()}-preview.pdf"',
        'Cache-Control': 'no-store',
    })


@router.get('/{day}/revisions/{revision}/pdf', dependencies=[Depends(require_viewer)])
def get_pdf(day: date, revision: int):
    data = repository.get_pdf(day.isoformat(), revision)
    if data is None:
        raise HTTPException(404, '저장된 PDF를 찾을 수 없습니다.')
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': f'inline; filename="worklog-{day.isoformat()}-v{revision}.pdf"',
        'Cache-Control': 'no-store',
    })
