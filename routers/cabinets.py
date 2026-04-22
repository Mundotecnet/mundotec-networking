from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc

router = APIRouter()


class CabinetCreate(BaseModel):
    name: str
    letter: str
    rack_units: Optional[int] = None
    notes: Optional[str] = None


class CabinetUpdate(BaseModel):
    name: Optional[str] = None
    letter: Optional[str] = None
    rack_units: Optional[int] = None
    notes: Optional[str] = None


class CabinetOut(BaseModel):
    id: int
    room_id: int
    name: str
    letter: str
    rack_units: Optional[int]
    notes: Optional[str]
    panel_count: int = 0

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, c: models.Cabinet) -> "CabinetOut":
        return cls(
            id=c.id, room_id=c.room_id, name=c.name,
            letter=c.letter.upper(), rack_units=c.rack_units,
            notes=c.notes, panel_count=len(c.patch_panels),
        )


@router.get("/rooms/{room_id}/cabinets", response_model=List[CabinetOut])
def list_cabinets(room_id: int, db: Session = Depends(get_db),
                  _: models.User = Depends(get_current_user)):
    cabinets = db.query(models.Cabinet).filter(
        models.Cabinet.room_id == room_id
    ).order_by(models.Cabinet.letter).all()
    return [CabinetOut.from_model(c) for c in cabinets]


@router.post("/rooms/{room_id}/cabinets", response_model=CabinetOut, status_code=201)
def create_cabinet(
    room_id: int, payload: CabinetCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    c = models.Cabinet(
        room_id=room_id,
        name=payload.name,
        letter=payload.letter.upper(),
        rack_units=payload.rack_units,
        notes=payload.notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, "CREATE", "cabinet", entity_id=c.id, entity_label=c.name,
                  client_id=room.client_id, user=current_user, request=request)
    return CabinetOut.from_model(c)


@router.get("/cabinets/{cabinet_id}", response_model=CabinetOut)
def get_cabinet(cabinet_id: int, db: Session = Depends(get_db),
                _: models.User = Depends(get_current_user)):
    c = db.query(models.Cabinet).filter(models.Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Gabinete no encontrado")
    return CabinetOut.from_model(c)


@router.put("/cabinets/{cabinet_id}", response_model=CabinetOut)
def update_cabinet(
    cabinet_id: int, payload: CabinetUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = db.query(models.Cabinet).filter(models.Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Gabinete no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v.upper() if k == "letter" else v)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, "UPDATE", "cabinet", entity_id=c.id, entity_label=c.name,
                  client_id=c.room.client_id, user=current_user, request=request)
    return CabinetOut.from_model(c)


@router.delete("/cabinets/{cabinet_id}")
def delete_cabinet(
    cabinet_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    c = db.query(models.Cabinet).filter(models.Cabinet.id == cabinet_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Gabinete no encontrado")
    audit_svc.log(db, "DELETE", "cabinet", entity_id=c.id, entity_label=c.name,
                  client_id=c.room.client_id, user=current_user, request=request)
    db.delete(c)
    db.commit()
    return {"message": "Gabinete eliminado"}
