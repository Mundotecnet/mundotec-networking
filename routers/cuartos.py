from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/cuartos", tags=["cuartos"])


class CuartoCreate(BaseModel):
    edificio_id: str
    piso: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None


class CuartoUpdate(BaseModel):
    piso: Optional[int] = None
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None


@router.get("")
def listar_cuartos(edificio_id: Optional[str] = None, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    q = """
        SELECT cu.*, e.nombre AS edificio_nombre, s.nombre AS sitio_nombre
        FROM cuarto cu
        JOIN edificio e ON e.id = cu.edificio_id
        JOIN sitio s ON s.id = e.sitio_id
    """
    params = {}
    if edificio_id:
        q += " WHERE cu.edificio_id = :eid"
        params["eid"] = edificio_id
    q += " ORDER BY e.codigo, cu.piso, cu.codigo"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{cuarto_id}")
def detalle_cuarto(cuarto_id: str, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT cu.*, e.nombre AS edificio_nombre, s.nombre AS sitio_nombre,
               s.id AS sitio_id
        FROM cuarto cu
        JOIN edificio e ON e.id = cu.edificio_id
        JOIN sitio s ON s.id = e.sitio_id
        WHERE cu.id = :id
    """), {"id": cuarto_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Cuarto no encontrado")

    gabinetes = db.execute(text(
        "SELECT * FROM gabinete WHERE cuarto_id = :cid ORDER BY codigo"
    ), {"cid": cuarto_id}).mappings().all()

    return {**dict(row), "gabinetes": [dict(g) for g in gabinetes]}


@router.post("", status_code=201)
def crear_cuarto(data: CuartoCreate, db: Session = Depends(get_db),
                 current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO cuarto (id, edificio_id, piso, codigo, nombre, descripcion)
        VALUES (:id, :eid, :piso, :cod, :nom, :desc)
    """), {"id": nuevo_id, "eid": data.edificio_id, "piso": data.piso,
           "cod": data.codigo, "nom": data.nombre, "desc": data.descripcion})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.patch("/{cuarto_id}")
def actualizar_cuarto(cuarto_id: str, data: CuartoUpdate, db: Session = Depends(get_db),
                      current_user=Depends(require_editor)):
    cambios = {k: v for k, v in data.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(400, "Sin cambios")
    sets = ", ".join(f"{k} = :{k}" for k in cambios)
    cambios["id"] = cuarto_id
    db.execute(text(f"UPDATE cuarto SET {sets} WHERE id = :id"), cambios)
    db.commit()
    return {"ok": True}


@router.delete("/{cuarto_id}")
def eliminar_cuarto(cuarto_id: str, db: Session = Depends(get_db),
                    current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM cuarto WHERE id = :id"), {"id": cuarto_id})
    db.commit()
    return {"ok": True}
