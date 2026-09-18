"""Hierarchy editing and scoped automatic vacancy filling API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.services.organization import (
    assign_vacancies, create_unit, delete_unit, hierarchy, move_unit,
)

router = APIRouter(prefix="/organization", tags=["organization"])


class UnitCreate(BaseModel):
    parent_id: int
    kind: str
    name: str = Field(min_length=1, max_length=100)


class UnitMove(BaseModel):
    parent_id: int


@router.get("")
def get_hierarchy(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return hierarchy(db)


@router.post("", status_code=201)
def add_unit(payload: UnitCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        node = create_unit(db, payload.parent_id, payload.kind, payload.name)
        return {"id": node.id}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.patch("/{node_id}/parent")
def change_parent(node_id: int, payload: UnitMove, db: Session = Depends(get_db)) -> dict[str, bool]:
    try:
        move_unit(db, node_id, payload.parent_id)
        return {"ok": True}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/{node_id}")
def remove_unit(node_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    try:
        delete_unit(db, node_id)
        return {"ok": True}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{node_id}/auto-fill")
def auto_fill_unit(node_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return assign_vacancies(db, node_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
