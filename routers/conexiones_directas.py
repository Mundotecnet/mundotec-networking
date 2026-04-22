from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor
from services import audit as audit_svc

router = APIRouter()

ACTIVO_RED_TYPES = {"switch", "router", "firewall", "ap", "servidor", "ups"}


class DirectConnCreate(BaseModel):
    port_a_id: int
    port_b_id: int
    cable_type: Optional[str] = None
    notes: Optional[str] = None


class PortInfo(BaseModel):
    id: int
    port_number: str
    port_label: Optional[str]
    port_mode: Optional[str]
    status: str

    model_config = {"from_attributes": True}


class DeviceWithPorts(BaseModel):
    id: int
    name: str
    device_type: str
    ports: List[PortInfo]


class DirectConnOut(BaseModel):
    id: int
    room_id: int
    cable_type: Optional[str]
    notes: Optional[str]
    device_a_id: int
    device_a_name: str
    device_a_type: str
    port_a_id: int
    port_a_number: str
    port_a_label: Optional[str]
    port_a_mode: Optional[str]
    device_b_id: int
    device_b_name: str
    device_b_type: str
    port_b_id: int
    port_b_number: str
    port_b_label: Optional[str]
    port_b_mode: Optional[str]


def _build_out(db: Session, c: models.Connection) -> DirectConnOut:
    pa = db.query(models.DevicePort).filter(models.DevicePort.id == c.node_a_id).first()
    pb = db.query(models.DevicePort).filter(models.DevicePort.id == c.node_b_id).first()
    da = db.query(models.Device).filter(models.Device.id == pa.device_id).first() if pa else None
    db_ = db.query(models.Device).filter(models.Device.id == pb.device_id).first() if pb else None

    extra = {}
    if c.description:
        try:
            import json
            extra = json.loads(c.description)
        except Exception:
            pass

    return DirectConnOut(
        id=c.id,
        room_id=c.room_id,
        cable_type=extra.get("cable_type"),
        notes=c.notes,
        device_a_id=da.id if da else 0,
        device_a_name=da.name if da else "?",
        device_a_type=da.device_type if da else "?",
        port_a_id=pa.id if pa else 0,
        port_a_number=pa.port_number if pa else "?",
        port_a_label=pa.port_label if pa else None,
        port_a_mode=pa.port_mode if pa else None,
        device_b_id=db_.id if db_ else 0,
        device_b_name=db_.name if db_ else "?",
        device_b_type=db_.device_type if db_ else "?",
        port_b_id=pb.id if pb else 0,
        port_b_number=pb.port_number if pb else "?",
        port_b_label=pb.port_label if pb else None,
        port_b_mode=pb.port_mode if pb else None,
    )


def _get_used_port_ids(db: Session, room_id: int) -> set:
    conns = db.query(models.Connection).filter(
        models.Connection.room_id == room_id,
        models.Connection.node_a_type == "device_port",
        models.Connection.node_b_type == "device_port",
    ).all()
    used = set()
    for c in conns:
        used.add(c.node_a_id)
        used.add(c.node_b_id)
    return used


@router.get("/rooms/{room_id}/direct-connections", response_model=List[DirectConnOut])
def list_direct_connections(
    room_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    conns = db.query(models.Connection).filter(
        models.Connection.room_id == room_id,
        models.Connection.node_a_type == "device_port",
        models.Connection.node_b_type == "device_port",
    ).order_by(models.Connection.id).all()
    return [_build_out(db, c) for c in conns]


@router.get("/rooms/{room_id}/direct-connections/devices", response_model=List[DeviceWithPorts])
def list_devices_with_ports(
    room_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    used = _get_used_port_ids(db, room_id)
    devs = db.query(models.Device).filter(
        models.Device.room_id == room_id,
        models.Device.category == "activo_red",
    ).order_by(models.Device.name).all()

    result = []
    for d in devs:
        ports = db.query(models.DevicePort).filter(
            models.DevicePort.device_id == d.id,
        ).order_by(models.DevicePort.port_number).all()
        libre_ports = [
            PortInfo(
                id=p.id,
                port_number=p.port_number,
                port_label=p.port_label,
                port_mode=p.port_mode,
                status=p.status,
            )
            for p in ports
            if p.id not in used
        ]
        result.append(DeviceWithPorts(
            id=d.id,
            name=d.name,
            device_type=d.device_type,
            ports=libre_ports,
        ))
    return result


@router.post("/rooms/{room_id}/direct-connections", response_model=DirectConnOut, status_code=201)
def create_direct_connection(
    room_id: int,
    payload: DirectConnCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")

    if payload.port_a_id == payload.port_b_id:
        raise HTTPException(status_code=422, detail="Los puertos deben ser diferentes")

    pa = db.query(models.DevicePort).filter(models.DevicePort.id == payload.port_a_id).first()
    pb = db.query(models.DevicePort).filter(models.DevicePort.id == payload.port_b_id).first()
    if not pa or not pb:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")

    used = _get_used_port_ids(db, room_id)
    if payload.port_a_id in used or payload.port_b_id in used:
        raise HTTPException(status_code=409, detail="Uno o ambos puertos ya están en uso en una conexión directa")

    import json
    extra = {}
    if payload.cable_type:
        extra["cable_type"] = payload.cable_type

    c = models.Connection(
        room_id=room_id,
        node_a_type="device_port",
        node_a_id=payload.port_a_id,
        node_b_type="device_port",
        node_b_id=payload.port_b_id,
        description=json.dumps(extra) if extra else None,
        notes=payload.notes,
    )
    db.add(c)

    pa.status = "ocupado"
    pb.status = "ocupado"

    db.commit()
    db.refresh(c)

    da = db.query(models.Device).filter(models.Device.id == pa.device_id).first()
    label = f"{da.name if da else '?'} p:{pa.port_number} ↔ p:{pb.port_number}"
    audit_svc.log(db, "CREATE", "direct_connection", entity_id=c.id, entity_label=label,
                  client_id=room.client_id, user=current_user, request=request)

    return _build_out(db, c)


@router.delete("/direct-connections/{conn_id}")
def delete_direct_connection(
    conn_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = db.query(models.Connection).filter(
        models.Connection.id == conn_id,
        models.Connection.node_a_type == "device_port",
        models.Connection.node_b_type == "device_port",
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conexión directa no encontrada")

    pa = db.query(models.DevicePort).filter(models.DevicePort.id == c.node_a_id).first()
    pb = db.query(models.DevicePort).filter(models.DevicePort.id == c.node_b_id).first()
    if pa:
        pa.status = "libre"
    if pb:
        pb.status = "libre"

    audit_svc.log(db, "DELETE", "direct_connection", entity_id=c.id,
                  client_id=c.room.client_id, user=current_user, request=request)

    db.delete(c)
    db.commit()
    return {"message": "Conexión directa eliminada"}
