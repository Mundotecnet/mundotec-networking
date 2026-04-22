from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc

router = APIRouter()


class BuildingCreate(BaseModel):
    name: str
    letter: str
    address: Optional[str] = None
    notes: Optional[str] = None


class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    letter: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class BuildingOut(BaseModel):
    id: int
    client_id: int
    name: str
    letter: str
    address: Optional[str]
    notes: Optional[str]
    room_count: int = 0

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, b: models.Building) -> "BuildingOut":
        return cls(
            id=b.id, client_id=b.client_id, name=b.name,
            letter=b.letter.upper(), address=b.address, notes=b.notes,
            room_count=len(b.rooms),
        )


@router.get("/clients/{client_id}/buildings", response_model=List[BuildingOut])
def list_buildings(client_id: int, db: Session = Depends(get_db),
                   _: models.User = Depends(get_current_user)):
    buildings = db.query(models.Building).filter(
        models.Building.client_id == client_id
    ).order_by(models.Building.letter).all()
    return [BuildingOut.from_model(b) for b in buildings]


@router.post("/clients/{client_id}/buildings", response_model=BuildingOut, status_code=201)
def create_building(
    client_id: int, payload: BuildingCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    if not db.query(models.Client).filter(models.Client.id == client_id).first():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    b = models.Building(
        client_id=client_id,
        name=payload.name,
        letter=payload.letter.upper(),
        address=payload.address,
        notes=payload.notes,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    audit_svc.log(db, "CREATE", "building", entity_id=b.id, entity_label=b.name,
                  client_id=client_id, user=current_user, request=request)
    return BuildingOut.from_model(b)


@router.get("/buildings/{building_id}", response_model=BuildingOut)
def get_building(building_id: int, db: Session = Depends(get_db),
                 _: models.User = Depends(get_current_user)):
    b = db.query(models.Building).filter(models.Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Edificio no encontrado")
    return BuildingOut.from_model(b)


@router.put("/buildings/{building_id}", response_model=BuildingOut)
def update_building(
    building_id: int, payload: BuildingUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    b = db.query(models.Building).filter(models.Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Edificio no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(b, k, v.upper() if k == "letter" else v)
    db.commit()
    db.refresh(b)
    audit_svc.log(db, "UPDATE", "building", entity_id=b.id, entity_label=b.name,
                  client_id=b.client_id, user=current_user, request=request)
    return BuildingOut.from_model(b)


@router.delete("/buildings/{building_id}")
def delete_building(
    building_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    b = db.query(models.Building).filter(models.Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Edificio no encontrado")
    audit_svc.log(db, "DELETE", "building", entity_id=b.id, entity_label=b.name,
                  client_id=b.client_id, user=current_user, request=request)
    db.delete(b)
    db.commit()
    return {"message": "Edificio eliminado"}
