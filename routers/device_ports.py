from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor

router = APIRouter()

VALID_MODES   = {None, "trunk", "access", "hybrid", "routed"}
VALID_STATUSES = {"activo", "ocupado", "libre", "inactivo"}


class PortCreate(BaseModel):
    port_number: str
    port_label: Optional[str] = None
    vlan_id: Optional[int] = None
    port_mode: Optional[str] = None
    poe_enabled: bool = False
    status: str = "libre"
    speed: Optional[str] = None
    patch_port_id: Optional[int] = None
    end_device_id: Optional[int] = None
    end_description: Optional[str] = None
    end_mac: Optional[str] = None
    end_ip: Optional[str] = None
    notes: Optional[str] = None


class PortUpdate(BaseModel):
    port_label: Optional[str] = None
    vlan_id: Optional[int] = None
    port_mode: Optional[str] = None
    poe_enabled: Optional[bool] = None
    status: Optional[str] = None
    speed: Optional[str] = None
    patch_port_id: Optional[int] = None
    end_device_id: Optional[int] = None
    end_description: Optional[str] = None
    end_mac: Optional[str] = None
    end_ip: Optional[str] = None
    notes: Optional[str] = None


class PortOut(BaseModel):
    id: int
    device_id: int
    port_number: str
    port_label: Optional[str]
    vlan_id: Optional[int]
    port_mode: Optional[str]
    poe_enabled: bool
    status: str
    speed: Optional[str]
    patch_port_id: Optional[int]
    end_device_id: Optional[int]
    end_description: Optional[str]
    end_mac: Optional[str]
    end_ip: Optional[str]
    notes: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/devices/{device_id}/ports", response_model=List[PortOut])
def list_ports(device_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    return db.query(models.DevicePort).filter(
        models.DevicePort.device_id == device_id
    ).order_by(models.DevicePort.port_number).all()


@router.post("/devices/{device_id}/ports", response_model=PortOut, status_code=201)
def create_port(
    device_id: int, payload: PortCreate, request: Request,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_editor),
):
    if not db.query(models.Device).filter(models.Device.id == device_id).first():
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    p = models.DevicePort(device_id=device_id, **payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.post("/devices/{device_id}/ports/generate")
def generate_ports(
    device_id: int,
    count: int = 24,
    port_type: str = "ethernet",
    db: Session = Depends(get_db),
    _: models.User = Depends(require_editor),
):
    if not db.query(models.Device).filter(models.Device.id == device_id).first():
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    existing = {p.port_number for p in db.query(models.DevicePort)
                .filter(models.DevicePort.device_id == device_id).all()}
    created = 0
    for i in range(1, count + 1):
        num = str(i)
        if num not in existing:
            db.add(models.DevicePort(device_id=device_id, port_number=num, port_label=port_type))
            created += 1
    db.commit()
    return {"created": created}


@router.get("/device-ports/{port_id}", response_model=PortOut)
def get_port(port_id: int, db: Session = Depends(get_db),
             _: models.User = Depends(get_current_user)):
    p = db.query(models.DevicePort).filter(models.DevicePort.id == port_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")
    return p


@router.put("/device-ports/{port_id}", response_model=PortOut)
def update_port(
    port_id: int, payload: PortUpdate, request: Request,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_editor),
):
    p = db.query(models.DevicePort).filter(models.DevicePort.id == port_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")
    data = payload.model_dump(exclude_unset=True)

    # Auto-determine status
    nodo_count = sum(1 for k in ("patch_port_id", "end_device_id", "end_description")
                     if data.get(k) or (k not in data and getattr(p, k)))
    if nodo_count > 0 and "status" not in data:
        data["status"] = "ocupado"

    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/device-ports/{port_id}")
def delete_port(
    port_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_editor),
):
    p = db.query(models.DevicePort).filter(models.DevicePort.id == port_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Puerto no encontrado")
    db.delete(p)
    db.commit()
    return {"message": "Puerto eliminado"}
