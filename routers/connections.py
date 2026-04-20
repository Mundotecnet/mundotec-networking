from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor
from services import audit as audit_svc

router = APIRouter()

VALID_NODE_TYPES = {"device_port", "patch_port", "device"}


def _resolve_node_label(db: Session, node_type: str, node_id: int) -> str:
    """Build a human-readable label for a connection endpoint."""
    if node_type == "device_port":
        p = db.query(models.DevicePort).filter(models.DevicePort.id == node_id).first()
        if not p:
            return f"device_port#{node_id}"
        d = db.query(models.Device).filter(models.Device.id == p.device_id).first()
        device_name = d.name if d else "?"
        vlan_label = ""
        if p.vlan_id:
            v = db.query(models.Vlan).filter(models.Vlan.id == p.vlan_id).first()
            if v:
                vlan_label = f"·VLAN {v.vlan_id}"
        poe = "·PoE" if p.poe_enabled else ""
        return f"{device_name} p:{p.port_number} ({p.port_mode or ''}{vlan_label}{poe})".strip()
    elif node_type == "patch_port":
        p = db.query(models.PatchPort).filter(models.PatchPort.id == node_id).first()
        if not p:
            return f"patch_port#{node_id}"
        pp = db.query(models.PatchPanel).filter(models.PatchPanel.id == p.patch_panel_id).first()
        pp_name = pp.name if pp else "?"
        return f"PP {pp_name} {p.label or p.number}"
    elif node_type == "device":
        d = db.query(models.Device).filter(models.Device.id == node_id).first()
        if not d:
            return f"device#{node_id}"
        detail = ""
        if d.mac:
            detail = f" {d.mac}"
        if d.ip:
            detail += f"·{d.ip}"
        return f"{d.name}{detail}"
    return f"{node_type}#{node_id}"


class ConnectionCreate(BaseModel):
    description: Optional[str] = None
    notes: Optional[str] = None
    node_a_type: str
    node_a_id: int
    node_b_type: str
    node_b_id: int


class ConnectionUpdate(BaseModel):
    description: Optional[str] = None
    notes: Optional[str] = None


class ConnectionOut(BaseModel):
    id: int
    room_id: int
    description: Optional[str]
    notes: Optional[str]
    node_a_type: str
    node_a_id: int
    node_b_type: str
    node_b_id: int
    chain: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/rooms/{room_id}/connections", response_model=List[ConnectionOut])
def list_connections(room_id: int, db: Session = Depends(get_db),
                     _: models.User = Depends(get_current_user)):
    conns = db.query(models.Connection).filter(
        models.Connection.room_id == room_id
    ).order_by(models.Connection.id).all()
    result = []
    for c in conns:
        a_label = _resolve_node_label(db, c.node_a_type, c.node_a_id)
        b_label = _resolve_node_label(db, c.node_b_type, c.node_b_id)
        chain = f"{a_label} ──► {b_label}"
        result.append(ConnectionOut(
            id=c.id, room_id=c.room_id, description=c.description,
            notes=c.notes, node_a_type=c.node_a_type, node_a_id=c.node_a_id,
            node_b_type=c.node_b_type, node_b_id=c.node_b_id, chain=chain,
        ))
    return result


@router.post("/rooms/{room_id}/connections", response_model=ConnectionOut, status_code=201)
def create_connection(
    room_id: int, payload: ConnectionCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")
    if payload.node_a_type not in VALID_NODE_TYPES or payload.node_b_type not in VALID_NODE_TYPES:
        raise HTTPException(status_code=422, detail="node_type inválido")
    c = models.Connection(room_id=room_id, **payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, "CREATE", "connection", entity_id=c.id, entity_label=c.description,
                  client_id=room.client_id, user=current_user, request=request)
    chain = f"{_resolve_node_label(db, c.node_a_type, c.node_a_id)} ──► {_resolve_node_label(db, c.node_b_type, c.node_b_id)}"
    return ConnectionOut(
        id=c.id, room_id=c.room_id, description=c.description, notes=c.notes,
        node_a_type=c.node_a_type, node_a_id=c.node_a_id,
        node_b_type=c.node_b_type, node_b_id=c.node_b_id, chain=chain,
    )


@router.put("/connections/{conn_id}", response_model=ConnectionOut)
def update_connection(
    conn_id: int, payload: ConnectionUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = db.query(models.Connection).filter(models.Connection.id == conn_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    chain = f"{_resolve_node_label(db, c.node_a_type, c.node_a_id)} ──► {_resolve_node_label(db, c.node_b_type, c.node_b_id)}"
    return ConnectionOut(
        id=c.id, room_id=c.room_id, description=c.description, notes=c.notes,
        node_a_type=c.node_a_type, node_a_id=c.node_a_id,
        node_b_type=c.node_b_type, node_b_id=c.node_b_id, chain=chain,
    )


@router.delete("/connections/{conn_id}")
def delete_connection(
    conn_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = db.query(models.Connection).filter(models.Connection.id == conn_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    audit_svc.log(db, "DELETE", "connection", entity_id=c.id,
                  client_id=c.room.client_id, user=current_user, request=request)
    db.delete(c)
    db.commit()
    return {"message": "Conexión eliminada"}
