from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/sitios", tags=["sitios"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class SitioCreate(BaseModel):
    cliente_id: int
    nombre: str
    direccion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    zona_horaria: Optional[str] = "America/Costa_Rica"


class SitioUpdate(BaseModel):
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    zona_horaria: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
def listar_sitios(cliente_id: Optional[int] = None, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    q = "SELECT s.*, c.name AS cliente_nombre FROM sitio s JOIN clients c ON c.id = s.cliente_id"
    params = {}
    if cliente_id:
        q += " WHERE s.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " ORDER BY c.name, s.nombre"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{sitio_id}")
def detalle_sitio(sitio_id: str, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT s.*, c.name AS cliente_nombre
        FROM sitio s JOIN clients c ON c.id = s.cliente_id
        WHERE s.id = :id
    """), {"id": sitio_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Sitio no encontrado")
    return dict(row)


@router.get("/{sitio_id}/topologia")
def topologia_sitio(sitio_id: str, db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    """Árbol completo: edificio → cuartos → gabinetes."""
    edificios = db.execute(text(
        "SELECT * FROM edificio WHERE sitio_id = :sid ORDER BY codigo"
    ), {"sid": sitio_id}).mappings().all()

    resultado = []
    for edif in edificios:
        cuartos = db.execute(text(
            "SELECT * FROM cuarto WHERE edificio_id = :eid ORDER BY piso, codigo"
        ), {"eid": str(edif["id"])}).mappings().all()

        cuartos_data = []
        for cu in cuartos:
            gabs = db.execute(text(
                "SELECT * FROM gabinete WHERE cuarto_id = :cid ORDER BY codigo"
            ), {"cid": str(cu["id"])}).mappings().all()
            cuartos_data.append({**dict(cu), "gabinetes": [dict(g) for g in gabs]})

        resultado.append({**dict(edif), "cuartos": cuartos_data})

    return {"sitio_id": sitio_id, "edificios": resultado}


@router.post("", status_code=201)
def crear_sitio(data: SitioCreate, db: Session = Depends(get_db),
                current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO sitio (id, cliente_id, nombre, direccion, latitud, longitud, zona_horaria)
        VALUES (:id, :cid, :nombre, :dir, :lat, :lon, :tz)
    """), {
        "id": nuevo_id, "cid": data.cliente_id, "nombre": data.nombre,
        "dir": data.direccion, "lat": data.latitud, "lon": data.longitud,
        "tz": data.zona_horaria,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.patch("/{sitio_id}")
def actualizar_sitio(sitio_id: str, data: SitioUpdate, db: Session = Depends(get_db),
                     current_user=Depends(require_editor)):
    cambios = {k: v for k, v in data.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(400, "Sin cambios")
    sets = ", ".join(f"{k} = :{k}" for k in cambios)
    cambios["id"] = sitio_id
    db.execute(text(f"UPDATE sitio SET {sets} WHERE id = :id"), cambios)
    db.commit()
    return {"ok": True}


@router.delete("/{sitio_id}")
def eliminar_sitio(sitio_id: str, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM sitio WHERE id = :id"), {"id": sitio_id})
    db.commit()
    return {"ok": True}
