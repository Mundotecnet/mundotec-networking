from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/edificios", tags=["edificios"])


class EdificioCreate(BaseModel):
    sitio_id: str
    codigo: str
    nombre: str
    piso_default: Optional[int] = 1


class EdificioUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    piso_default: Optional[int] = None


@router.get("")
def listar_edificios(sitio_id: Optional[str] = None, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    q = "SELECT e.*, s.nombre AS sitio_nombre FROM edificio e JOIN sitio s ON s.id = e.sitio_id"
    params = {}
    if sitio_id:
        q += " WHERE e.sitio_id = :sid"
        params["sid"] = sitio_id
    q += " ORDER BY s.nombre, e.codigo"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{edificio_id}")
def detalle_edificio(edificio_id: str, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT e.*, s.nombre AS sitio_nombre
        FROM edificio e JOIN sitio s ON s.id = e.sitio_id
        WHERE e.id = :id
    """), {"id": edificio_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Edificio no encontrado")
    return dict(row)


@router.post("", status_code=201)
def crear_edificio(data: EdificioCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO edificio (id, sitio_id, codigo, nombre, piso_default)
        VALUES (:id, :sid, :cod, :nom, :piso)
    """), {"id": nuevo_id, "sid": data.sitio_id, "cod": data.codigo,
           "nom": data.nombre, "piso": data.piso_default})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.patch("/{edificio_id}")
def actualizar_edificio(edificio_id: str, data: EdificioUpdate, db: Session = Depends(get_db),
                        current_user=Depends(require_editor)):
    cambios = {k: v for k, v in data.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(400, "Sin cambios")
    sets = ", ".join(f"{k} = :{k}" for k in cambios)
    cambios["id"] = edificio_id
    db.execute(text(f"UPDATE edificio SET {sets} WHERE id = :id"), cambios)
    db.commit()
    return {"ok": True}


@router.delete("/{edificio_id}")
def eliminar_edificio(edificio_id: str, db: Session = Depends(get_db),
                      current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM edificio WHERE id = :id"), {"id": edificio_id})
    db.commit()
    return {"ok": True}
