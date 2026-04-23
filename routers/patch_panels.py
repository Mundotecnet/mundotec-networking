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

LABEL_SIMPLE   = re.compile(r"^[0-9][A-Z]-[A-Z][0-9]{2}$")
LABEL_FULL     = re.compile(r"^[0-9][A-Z]-[A-Z]-[A-Z][0-9]{2}$")
LABEL_EXTENDED = re.compile(r"^[0-9]-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+-[0-9]{2}$")


def _generate_label(pp: models.PatchPanel, number: int, client_fmt: str = None) -> str:
    n = f"{number:02d}"
    fmt = client_fmt or pp.format or "simple"
    if fmt == "edificio_cuarto_rack":
        # EDIFICIO-CUARTO-RACK-PANEL-00
        edificio = pp.building or "A"
        cuarto = pp.room_letter or "A"
        rack = pp.rack_id or "A"
        panel = pp.panel_letter or "A"
        return f"{edificio}-{cuarto}-{rack}-{panel}-{n}"
    if fmt == "extended":
        return (
            f"{pp.floor}-{pp.building or 'A'}-{pp.room_letter}-"
            f"{pp.rack_id or 'A'}-{pp.panel_letter}-{n}"
        )
    if fmt == "full":
        return f"{pp.floor}{pp.room_letter}-{pp.building or 'A'}-{pp.panel_letter}{n}"
    # simple (default)
    return f"{pp.floor}{pp.room_letter}-{pp.panel_letter}{n}"


def _validate_label(label: str, fmt: str) -> bool:
    if fmt == "extended":
        return bool(LABEL_EXTENDED.match(label))
    if fmt == "full":
        return bool(LABEL_FULL.match(label))
    return bool(LABEL_SIMPLE.match(label))


class PPCreate(BaseModel):
    name: str
    cabinet_id: Optional[int] = None
    floor: int = 1
    building: Optional[str] = None
    room_letter: str = "A"
    panel_letter: str = "A"
    rack_id: Optional[str] = None
    format: str = "simple"
    notes: Optional[str] = None


class PPUpdate(BaseModel):
    name: Optional[str] = None
    cabinet_id: Optional[int] = None
    floor: Optional[int] = None
    building: Optional[str] = None
    room_letter: Optional[str] = None
    panel_letter: Optional[str] = None
    rack_id: Optional[str] = None
    format: Optional[str] = None
    notes: Optional[str] = None


class PPOut(BaseModel):
    id: int
    room_id: int
    cabinet_id: Optional[int]
    name: str
    floor: int
    building: Optional[str]
    room_letter: str
    panel_letter: str
    rack_id: Optional[str]
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
    dup_q = db.query(models.PatchPanel).filter(
        models.PatchPanel.panel_letter == payload.panel_letter.upper()
    )
    if payload.cabinet_id:
        dup_q = dup_q.filter(models.PatchPanel.cabinet_id == payload.cabinet_id)
    else:
        dup_q = dup_q.filter(models.PatchPanel.room_id == room_id,
                              models.PatchPanel.cabinet_id.is_(None))
    if dup_q.first():
        raise HTTPException(status_code=409,
            detail=f"Letra de panel '{payload.panel_letter.upper()}' ya existe en este gabinete/rack")
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
    updates = payload.model_dump(exclude_unset=True)
    if "panel_letter" in updates:
        new_letter = updates["panel_letter"].upper()
        updates["panel_letter"] = new_letter
        cab_id = updates.get("cabinet_id", pp.cabinet_id)
        dup_q = db.query(models.PatchPanel).filter(
            models.PatchPanel.panel_letter == new_letter,
            models.PatchPanel.id != pp_id
        )
        if cab_id:
            dup_q = dup_q.filter(models.PatchPanel.cabinet_id == cab_id)
        else:
            dup_q = dup_q.filter(models.PatchPanel.room_id == pp.room_id,
                                  models.PatchPanel.cabinet_id.is_(None))
        if dup_q.first():
            raise HTTPException(status_code=409,
                detail=f"Letra de panel '{new_letter}' ya existe en este gabinete/rack")
    for k, v in updates.items():
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


@router.post("/patch-panels/{pp_id}/regenerate-labels")
def regenerate_labels(
    pp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == pp_id).first()
    if not pp:
        raise HTTPException(status_code=404, detail="Patch panel no encontrado")

    # Get client label_format
    room = db.query(models.Room).filter(models.Room.id == pp.room_id).first()
    client = db.query(models.Client).filter(models.Client.id == room.client_id).first() if room else None
    client_fmt = client.label_format if client and client.label_format else None

    updated = 0
    for port in pp.ports:
        new_label = _generate_label(pp, port.number, client_fmt)
        if port.label != new_label:
            port.label = new_label
            updated += 1

    db.commit()
    audit_svc.log(db, "REGENERATE_LABELS", "patch_panel", entity_id=pp.id,
                  entity_label=pp.name, client_id=room.client_id if room else None,
                  user=current_user, request=request,
                  new_values={"format": client_fmt, "updated": updated})
    return {"updated": updated, "format": client_fmt or pp.format, "panel": pp.name}
