from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc

router = APIRouter()

VALID_FORMATS = {"simple", "full", "extended"}


class RoomCreate(BaseModel):
    name: str
    letter: Optional[str] = None
    building_id: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    switch_model: Optional[str] = None
    switch_mac: Optional[str] = None
    switch_ip: Optional[str] = None
    ap_model: Optional[str] = None
    ap_mac: Optional[str] = None
    ap_ip: Optional[str] = None
    patch_label_format: str = "simple"


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    letter: Optional[str] = None
    building_id: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    switch_model: Optional[str] = None
    switch_mac: Optional[str] = None
    switch_ip: Optional[str] = None
    ap_model: Optional[str] = None
    ap_mac: Optional[str] = None
    ap_ip: Optional[str] = None
    patch_label_format: Optional[str] = None


class RoomOut(BaseModel):
    id: int
    client_id: int
    building_id: Optional[int]
    letter: Optional[str]
    name: str
    location: Optional[str]
    notes: Optional[str]
    switch_model: Optional[str]
    switch_mac: Optional[str]
    switch_ip: Optional[str]
    ap_model: Optional[str]
    ap_mac: Optional[str]
    ap_ip: Optional[str]
    patch_label_format: str

    model_config = {"from_attributes": True}


@router.get("/clients/{client_id}/rooms", response_model=List[RoomOut])
def list_rooms(client_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    return db.query(models.Room).filter(models.Room.client_id == client_id).order_by(models.Room.name).all()


@router.post("/clients/{client_id}/rooms", response_model=RoomOut, status_code=201)
def create_room(
    client_id: int, payload: RoomCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    if not db.query(models.Client).filter(models.Client.id == client_id).first():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if payload.patch_label_format not in VALID_FORMATS:
        raise HTTPException(status_code=422, detail="Formato de etiqueta inválido")
    r = models.Room(client_id=client_id, **payload.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    audit_svc.log(db, "CREATE", "room", entity_id=r.id, entity_label=r.name,
                  client_id=client_id, user=current_user, request=request)
    return r


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db),
             _: models.User = Depends(get_current_user)):
    r = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    return r


@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int, payload: RoomUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    r = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    old = {k: getattr(r, k) for k in payload.model_dump().keys()}
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    audit_svc.log(db, "UPDATE", "room", entity_id=r.id, entity_label=r.name,
                  client_id=r.client_id, old_values=old,
                  new_values=payload.model_dump(exclude_unset=True),
                  user=current_user, request=request)
    return r


@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    r = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    audit_svc.log(db, "DELETE", "room", entity_id=r.id, entity_label=r.name,
                  client_id=r.client_id, user=current_user, request=request)
    db.delete(r)
    db.commit()
    return {"message": "Cuarto eliminado"}
