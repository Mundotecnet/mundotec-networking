from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc
from services.crypto import encrypt, decrypt

router = APIRouter()

ACTIVO_RED_TYPES   = {"switch", "router", "firewall", "ap", "servidor", "ups"}
ACTIVO_FINAL_TYPES = {"pc", "impresora", "nvr", "dvr", "camara", "pbx", "reloj_marcador", "otro"}
ALL_TYPES = ACTIVO_RED_TYPES | ACTIVO_FINAL_TYPES


class DeviceCreate(BaseModel):
    category: str
    name: str
    device_type: str
    brand: str = ""
    model: str = ""
    mac: Optional[str] = None
    ip: Optional[str] = None
    hostname: Optional[str] = None
    admin_port: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    notes: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    mac: Optional[str] = None
    ip: Optional[str] = None
    hostname: Optional[str] = None
    admin_port: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    notes: Optional[str] = None


class DeviceOut(BaseModel):
    id: int
    room_id: int
    category: str
    name: str
    device_type: str
    brand: str
    model: str
    mac: Optional[str]
    ip: Optional[str]
    hostname: Optional[str]
    admin_port: Optional[str]
    notes: Optional[str]
    has_credentials: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, d: models.Device) -> "DeviceOut":
        return cls(
            id=d.id, room_id=d.room_id, category=d.category, name=d.name,
            device_type=d.device_type, brand=d.brand, model=d.model,
            mac=d.mac, ip=d.ip, hostname=d.hostname, admin_port=d.admin_port,
            notes=d.notes,
            has_credentials=bool(d.username_encrypted or d.password_encrypted),
        )


class CredentialsOut(BaseModel):
    username: Optional[str]
    password: Optional[str]


@router.get("/rooms/{room_id}/devices")
def list_devices(room_id: int, db: Session = Depends(get_db),
                 _: models.User = Depends(get_current_user)):
    devs = db.query(models.Device).filter(models.Device.room_id == room_id).order_by(models.Device.name).all()
    red   = [DeviceOut.from_model(d) for d in devs if d.category == "activo_red"]
    final = [DeviceOut.from_model(d) for d in devs if d.category == "activo_final"]
    return {"activo_red": red, "activo_final": final}


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    d = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return DeviceOut.from_model(d)


@router.get("/devices/{device_id}/credentials", response_model=CredentialsOut)
def get_credentials(
    device_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    d = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    try:
        username = decrypt(d.username_encrypted) if d.username_encrypted else None
        password = decrypt(d.password_encrypted) if d.password_encrypted else None
    except Exception:
        raise HTTPException(status_code=500, detail="Error al descifrar credenciales")
    audit_svc.log(db, "VIEW_CREDENTIALS", "device", entity_id=d.id, entity_label=d.name,
                  client_id=d.room.client_id, user=current_user, request=request)
    return CredentialsOut(username=username, password=password)


@router.post("/rooms/{room_id}/devices", response_model=DeviceOut, status_code=201)
def create_device(
    room_id: int, payload: DeviceCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Cuarto no encontrado")

    valid = ACTIVO_RED_TYPES if payload.category == "activo_red" else ACTIVO_FINAL_TYPES
    if payload.device_type not in valid:
        raise HTTPException(status_code=422, detail=f"device_type inválido para categoría {payload.category}")

    d = models.Device(
        room_id=room_id,
        category=payload.category,
        name=payload.name,
        device_type=payload.device_type,
        brand=payload.brand,
        model=payload.model,
        mac=payload.mac,
        ip=payload.ip,
        hostname=payload.hostname,
        admin_port=payload.admin_port,
        notes=payload.notes,
        username_encrypted=encrypt(payload.username) if payload.username else None,
        password_encrypted=encrypt(payload.password) if payload.password else None,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    audit_svc.log(db, "CREATE", "device", entity_id=d.id, entity_label=d.name,
                  client_id=room.client_id, user=current_user, request=request,
                  new_values={"name": d.name, "device_type": d.device_type, "ip": d.ip})
    return DeviceOut.from_model(d)


@router.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int, payload: DeviceUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    d = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    old = {"name": d.name, "ip": d.ip, "mac": d.mac}
    data = payload.model_dump(exclude_unset=True)
    if "username" in data:
        d.username_encrypted = encrypt(data.pop("username")) if data["username"] else None
    else:
        data.pop("username", None)
    if "password" in data:
        d.password_encrypted = encrypt(data.pop("password")) if data["password"] else None
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    audit_svc.log(db, "UPDATE", "device", entity_id=d.id, entity_label=d.name,
                  client_id=d.room.client_id, old_values=old, new_values=data,
                  user=current_user, request=request)
    return DeviceOut.from_model(d)


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    d = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    audit_svc.log(db, "DELETE", "device", entity_id=d.id, entity_label=d.name,
                  client_id=d.room.client_id, user=current_user, request=request)
    db.delete(d)
    db.commit()
    return {"message": "Dispositivo eliminado"}
