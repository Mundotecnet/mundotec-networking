from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/gabinetes", tags=["gabinetes"])


class GabineteCreate(BaseModel):
    cuarto_id: str
    codigo: str
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None
    unidades_rack: Optional[int] = None


class GabineteUpdate(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    ubicacion: Optional[str] = None
    unidades_rack: Optional[int] = None


@router.get("")
def listar_gabinetes(cuarto_id: Optional[str] = None, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    q = """
        SELECT g.*, cu.nombre AS cuarto_nombre, e.nombre AS edificio_nombre
        FROM gabinete g
        JOIN cuarto cu ON cu.id = g.cuarto_id
        JOIN edificio e ON e.id = cu.edificio_id
    """
    params = {}
    if cuarto_id:
        q += " WHERE g.cuarto_id = :cid"
        params["cid"] = cuarto_id
    q += " ORDER BY cu.nombre, g.codigo"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{gabinete_id}")
def detalle_gabinete(gabinete_id: str, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT g.*, cu.nombre AS cuarto_nombre, e.nombre AS edificio_nombre
        FROM gabinete g
        JOIN cuarto cu ON cu.id = g.cuarto_id
        JOIN edificio e ON e.id = cu.edificio_id
        WHERE g.id = :id
    """), {"id": gabinete_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Gabinete no encontrado")
    return dict(row)


@router.post("", status_code=201)
def crear_gabinete(data: GabineteCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO gabinete (id, cuarto_id, codigo, nombre, ubicacion, unidades_rack)
        VALUES (:id, :cid, :cod, :nom, :ubi, :rack)
    """), {"id": nuevo_id, "cid": data.cuarto_id, "cod": data.codigo,
           "nom": data.nombre, "ubi": data.ubicacion, "rack": data.unidades_rack})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.patch("/{gabinete_id}")
def actualizar_gabinete(gabinete_id: str, data: GabineteUpdate, db: Session = Depends(get_db),
                        current_user=Depends(require_editor)):
    cambios = {k: v for k, v in data.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(400, "Sin cambios")
    sets = ", ".join(f"{k} = :{k}" for k in cambios)
    cambios["id"] = gabinete_id
    db.execute(text(f"UPDATE gabinete SET {sets} WHERE id = :id"), cambios)
    db.commit()
    return {"ok": True}


@router.delete("/{gabinete_id}")
def eliminar_gabinete(gabinete_id: str, db: Session = Depends(get_db),
                      current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM gabinete WHERE id = :id"), {"id": gabinete_id})
    db.commit()
    return {"ok": True}
