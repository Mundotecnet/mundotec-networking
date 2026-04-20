from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor
from services import audit as audit_svc

router = APIRouter()


class VlanCreate(BaseModel):
    vlan_id: int
    name: str
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    dhcp: bool = False
    notes: Optional[str] = None


class VlanUpdate(BaseModel):
    vlan_id: Optional[int] = None
    name: Optional[str] = None
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    dhcp: Optional[bool] = None
    notes: Optional[str] = None


class VlanOut(BaseModel):
    id: int
    room_id: int
    vlan_id: int
    name: str
    subnet: Optional[str]
    gateway: Optional[str]
    dhcp: bool
    notes: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/rooms/{room_id}/vlans", response_model=List[VlanOut])
def list_vlans(room_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    return db.query(models.Vlan).filter(models.Vlan.room_id == room_id).order_by(models.Vlan.vlan_id).all()


@router.post("/rooms/{room_id}/vlans", response_model=VlanOut, status_code=201)
def create_vlan(
    room_id: int, payload: VlanCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    if not (1 <= payload.vlan_id <= 4094):
        raise HTTPException(status_code=422, detail="VLAN ID debe estar entre 1 y 4094")
    v = models.Vlan(room_id=room_id, **payload.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    audit_svc.log(db, "CREATE", "vlan", entity_id=v.id, entity_label=v.name,
                  client_id=room.client_id, user=current_user, request=request)
    return v


@router.put("/rooms/{room_id}/vlans/{vlan_id}", response_model=VlanOut)
def update_vlan(
    room_id: int, vlan_id: int, payload: VlanUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    v = db.query(models.Vlan).filter(
        models.Vlan.id == vlan_id, models.Vlan.room_id == room_id
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="VLAN no encontrada")
    for k, val in payload.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    audit_svc.log(db, "UPDATE", "vlan", entity_id=v.id, entity_label=v.name,
                  client_id=v.room.client_id, user=current_user, request=request)
    return v


@router.delete("/rooms/{room_id}/vlans/{vlan_id}")
def delete_vlan(
    room_id: int, vlan_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    v = db.query(models.Vlan).filter(
        models.Vlan.id == vlan_id, models.Vlan.room_id == room_id
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="VLAN no encontrada")
    audit_svc.log(db, "DELETE", "vlan", entity_id=v.id, entity_label=v.name,
                  client_id=v.room.client_id, user=current_user, request=request)
    db.delete(v)
    db.commit()
    return {"message": "VLAN eliminada"}
