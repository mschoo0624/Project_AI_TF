from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.user import User
from user.app.schemas.prosecution_document import DraftCreate, DraftUpdate
from user.app.services import prosecution_documents
from user.app.services.auth import require_scheduler, require_viewer


router = APIRouter(prefix='/prosecution-documents', tags=['prosecution-documents'])


@router.get('', dependencies=[Depends(require_viewer)])
def list_documents(db: Session = Depends(get_db)):
    return prosecution_documents.list_documents(db)


@router.get('/{identifier}', dependencies=[Depends(require_viewer)])
def get_document(identifier: UUID, db: Session = Depends(get_db)):
    return prosecution_documents.get_document(db, identifier)


@router.post('', status_code=201)
def create_document(payload: DraftCreate, db: Session = Depends(get_db),
                    actor: User = Depends(require_scheduler)):
    return prosecution_documents.create_document(db, payload, actor.username)


@router.put('/{identifier}')
def update_document(identifier: UUID, payload: DraftUpdate, db: Session = Depends(get_db),
                    actor: User = Depends(require_scheduler)):
    return prosecution_documents.update_document(db, identifier, payload, actor.username)
