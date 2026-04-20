import re
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc
from services.completeness import evaluate_port, pp_score

router = APIRouter()

LABEL_SIMPLE = re.compile(r"^[0-9][A-Z]-[A-Z][0-9]{2}$")
LABEL_FULL   = re.compile(r"^[0-9][A-Z]-[A-Z]-[A-Z][0-9]{2}$")


def _generate_label(pp: models.PatchPanel, number: int) -> str:
    n = f"{number:02d}"
    if pp.format == "full":
        return f"{pp.floor}{pp.room_letter}-{pp.building or 'A'}-{pp.panel_letter}{n}"
    return f"{pp.floor}{pp.room_letter}-{pp.panel_letter}{n}"


def _validate_label(label: str, fmt: str) -> bool:
    if fmt == "full":
        return bool(LABEL_FULL.match(label))
    return bool(LABEL_SIMPLE.match(label))


class PPCreate(BaseModel):
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    floor: int = 1
    building: Optional[str] = None
    room_letter: str = "A"
    panel_letter: str = "A"
    format: str = "simple"
    notes: Optional[str] = None


class PPUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    floor: Optional[int] = None
    building: Optional[str] = None
    room_letter: Optional[str] = None
    panel_letter: Optional[str] = None
    format: Optional[str] = None
    notes: Optional[str] = None


class PPOut(BaseModel):
    id: int
    room_id: int
    name: str
    brand: Optional[str]
    model: Optional[str]
    floor: int
    building: Optional[str]
    room_letter: str
    panel_letter: str
    format: str
    notes: Optional[str]

    model_config = {"from_attributes": True}


class PortOut(BaseModel):
    id: int
    number: int
    label: Optional[str]
    status: str
    completeness_status: str
    node_type: Optional[str]
    device_id: Optional[int]
    node_description: Optional[str]
    node_mac: Optional[str]
    node_ip: Optional[str]
    vlan_id: Optional[int]
    switch_port_id: Optional[int]
    notes: Optional[str]
    confirmed_by: Optional[int]
    confirmation_notes: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/rooms/{room_id}/patch-panels", response_model=List[PPOut])
def list_panels(room_id: int, db: Session = Depends(get_db),
                _: models.User = Depends(get_current_user)):
    return db.query(models.PatchPanel).filter(
        models.PatchPanel.room_id == room_id
    ).order_by(models.PatchPanel.name).all()


@router.post("/rooms/{room_id}/patch-panels", response_model=PPOut, status_code=201)
def create_panel(
    room_id: int, payload: PPCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    pp = models.PatchPanel(room_id=room_id, **payload.model_dump())
    db.add(pp)
    db.flush()

    # Auto-generate 24 ports
    for n in range(1, 25):
        label = _generate_label(pp, n)
        port = models.PatchPort(
            patch_panel_id=pp.id,
            number=n,
            label=label,
            status="sin_revisar",
            completeness_status="sin_revisar",
        )
        db.add(port)

    db.commit()
    db.refresh(pp)
    audit_svc.log(db, "CREATE", "patch_panel", entity_id=pp.id, entity_label=pp.name,
                  client_id=room.client_id, user=current_user, request=request)
    return pp


@router.get("/patch-panels/{pp_id}", response_model=PPOut)
def get_panel(pp_id: int, db: Session = Depends(get_db),
              _: models.User = Depends(get_current_user)):
    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == pp_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Patch panel no encontrado")
    return pp


@router.put("/patch-panels/{pp_id}", response_model=PPOut)
def update_panel(
    pp_id: int, payload: PPUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == pp_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Patch panel no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(pp, k, v)
    db.commit()
    db.refresh(pp)
    audit_svc.log(db, "UPDATE", "patch_panel", entity_id=pp.id, entity_label=pp.name,
                  client_id=pp.room.client_id, user=current_user, request=request)
    return pp


@router.delete("/patch-panels/{pp_id}")
def delete_panel(
    pp_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == pp_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Patch panel no encontrado")
    audit_svc.log(db, "DELETE", "patch_panel", entity_id=pp.id, entity_label=pp.name,
                  client_id=pp.room.client_id, user=current_user, request=request)
    db.delete(pp)
    db.commit()
    return {"message": "Patch panel eliminado"}


@router.get("/patch-panels/{pp_id}/ports", response_model=List[PortOut])
def list_ports(pp_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == pp_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Patch panel no encontrado")
    room = pp.room
    room_has_switch = bool(room.switch_ip or room.switch_mac or room.switch_model)
    for port in pp.ports:
        port.completeness_status = evaluate_port(port, room_has_switch)
    db.commit()
    return pp.ports
