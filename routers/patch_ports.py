import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from database import get_db
import models
from auth.jwt import get_current_user, require_editor
from services import audit as audit_svc
from services.completeness import evaluate_port

router = APIRouter()

LABEL_SIMPLE   = re.compile(r"^[0-9][A-Z]-[A-Z][0-9]{2}$")
LABEL_FULL     = re.compile(r"^[0-9][A-Z]-[A-Z]-[A-Z][0-9]{2}$")
LABEL_EXTENDED = re.compile(r"^[0-9]-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[0-9]{2}$")


def _check_label_unique(db: Session, room_id: int, label: str, exclude_port_id: int | None = None):
    """Validate label uniqueness within a room."""
    query = (
        db.query(models.PatchPort)
        .join(models.PatchPanel)
        .filter(models.PatchPanel.room_id == room_id, models.PatchPort.label == label)
    )
    if exclude_port_id:
        query = query.filter(models.PatchPort.id != exclude_port_id)
    if query.first():
        raise HTTPException(status_code=400, detail=f"Etiqueta '{label}' ya existe en este cuarto")


class PortUpdate(BaseModel):
    label: Optional[str] = None
    node_type: Optional[str] = None
    device_id: Optional[int] = None
    node_description: Optional[str] = None
    node_mac: Optional[str] = None
    node_ip: Optional[str] = None
    vlan_id: Optional[int] = None
    switch_port_id: Optional[int] = None
    notes: Optional[str] = None


class ConfirmBody(BaseModel):
    node_type: str  # "libre" | "prevista"
    confirmation_notes: Optional[str] = None


class PortOut(BaseModel):
    id: int
    patch_panel_id: int
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
    confirmed_at: Optional[datetime]
    confirmation_notes: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/patch-ports/{port_id}", response_model=PortOut)
def get_port(port_id: int, db: Session = Depends(get_db),
             _: models.User = Depends(get_current_user)):
    p = db.query(models.PatchPort).filter(models.PatchPort.id == port_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")
    return p


@router.put("/patch-ports/{port_id}", response_model=PortOut)
def update_port(
    port_id: int, payload: PortUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    port = db.query(models.PatchPort).filter(models.PatchPort.id == port_id).first()
    if not port:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")

    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == port.patch_panel_id).first()
    room = pp.room

    if payload.label and payload.label != port.label:
        fmt = pp.format
        if fmt == "extended":
            pattern = LABEL_EXTENDED
        elif fmt == "full":
            pattern = LABEL_FULL
        else:
            pattern = LABEL_SIMPLE
        if not pattern.match(payload.label):
            raise HTTPException(status_code=400, detail="Formato de etiqueta inválido")
        _check_label_unique(db, room.id, payload.label, exclude_port_id=port_id)

    old = {
        "label": port.label, "node_type": port.node_type,
        "node_mac": port.node_mac, "node_ip": port.node_ip,
        "vlan_id": port.vlan_id, "switch_port_id": port.switch_port_id,
    }

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(port, k, v)

    room_has_switch = bool(room.switch_ip or room.switch_mac or room.switch_model)
    port.completeness_status = evaluate_port(port, room_has_switch)
    port.status = port.completeness_status

    db.commit()
    db.refresh(port)
    audit_svc.log(
        db, "UPDATE", "patch_port", entity_id=port.id, entity_label=port.label,
        client_id=room.client_id,
        old_values=old, new_values=payload.model_dump(exclude_unset=True),
        user=current_user, request=request,
    )
    return port


@router.post("/patch-ports/{port_id}/confirm", response_model=PortOut)
def confirm_port(
    port_id: int, body: ConfirmBody, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    port = db.query(models.PatchPort).filter(models.PatchPort.id == port_id).first()
    if not port:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")
    if body.node_type not in ("libre", "prevista"):
        raise HTTPException(status_code=422, detail="node_type debe ser 'libre' o 'prevista'")

    port.node_type = body.node_type
    port.status = body.node_type
    port.completeness_status = body.node_type
    port.confirmed_by = current_user.id
    port.confirmed_at = datetime.now(timezone.utc)
    port.confirmation_notes = body.confirmation_notes

    db.commit()
    db.refresh(port)

    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == port.patch_panel_id).first()
    audit_svc.log(
        db, "CONFIRM_PORT", "patch_port", entity_id=port.id, entity_label=port.label,
        client_id=pp.room.client_id,
        new_values={"node_type": body.node_type},
        user=current_user, request=request,
    )
    return port
