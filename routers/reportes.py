"""Router de generación de reportes — MundoTec."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid, json
from datetime import datetime
from pathlib import Path

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/reportes", tags=["reportes"])

STORAGE = Path("storage/reportes")
MIME = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
EXT = {"pdf": ".pdf", "xlsx": ".xlsx", "docx": ".docx"}


class ReporteRequest(BaseModel):
    tipo: str           # infraestructura | trazabilidad | mantenimiento | ejecutivo | inventario | postmortem
    cliente_id: int
    formato: Optional[str] = None   # pdf | xlsx | docx (default según tipo)
    params: Optional[dict] = {}


def _crear_registro(db, reporte_id, tipo, cliente_id, formato, usuario_id):
    db.execute(text("""
        INSERT INTO reporte_historial (id, tipo, cliente_id, formato, estado, usuario_id, creado_en)
        VALUES (:id, :tipo, :cid, :fmt, 'procesando', :uid, now())
    """), {"id": reporte_id, "tipo": tipo, "cid": cliente_id, "fmt": formato, "uid": usuario_id})
    db.commit()


def _actualizar_estado(db, reporte_id, estado, ruta=None, error=None):
    db.execute(text("""
        UPDATE reporte_historial
        SET estado=:est, ruta_archivo=:ruta, error=:err, completado_en=now()
        WHERE id=:id
    """), {"id": reporte_id, "est": estado, "ruta": str(ruta) if ruta else None, "err": error})
    db.commit()


def _generar_bg(reporte_id: str, tipo: str, cliente_id: int, formato: str, params: dict, usuario_id: int):
    from database import SessionLocal
    from reportes.catalogo import CATALOGO
    db = SessionLocal()
    try:
        Clase = CATALOGO.get(tipo)
        if not Clase:
            _actualizar_estado(db, reporte_id, "error", error=f"Tipo desconocido: {tipo}")
            return
        rpt = Clase(cliente_id=cliente_id, formato=formato, params=params, db=db)
        rpt.reporte_id = reporte_id
        ruta = rpt.generar()
        _actualizar_estado(db, reporte_id, "listo", ruta=ruta)
    except Exception as e:
        _actualizar_estado(db, reporte_id, "error", error=str(e))
    finally:
        db.close()


@router.post("", status_code=202)
def solicitar_reporte(
    req: ReporteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_editor),
):
    from reportes.catalogo import CATALOGO
    if req.tipo not in CATALOGO:
        raise HTTPException(400, f"Tipo de reporte no válido. Opciones: {list(CATALOGO)}")

    Clase = CATALOGO[req.tipo]
    formato = req.formato or Clase.formato_default
    if formato not in MIME:
        raise HTTPException(400, f"Formato no soportado: {formato}")

    reporte_id = str(uuid.uuid4())

    # Crear tabla si no existe (bootstrap)
    _bootstrap_tabla(db)
    _crear_registro(db, reporte_id, req.tipo, req.cliente_id, formato, current_user.id)
    background_tasks.add_task(
        _generar_bg, reporte_id, req.tipo, req.cliente_id, formato, req.params or {}, current_user.id
    )
    return {"reporte_id": reporte_id, "estado": "procesando",
            "tipo": req.tipo, "formato": formato}


@router.get("")
def listar_reportes(
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _bootstrap_tabla(db)
    q = """
        SELECT rh.id::text, rh.tipo, rh.formato, rh.estado, rh.creado_en, rh.completado_en,
               rh.error, c.name AS cliente_nombre, u.username AS usuario
        FROM reporte_historial rh
        LEFT JOIN clients c ON c.id = rh.cliente_id
        LEFT JOIN users u ON u.id = rh.usuario_id
        WHERE 1=1
    """
    params = {}
    if cliente_id:
        q += " AND rh.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " ORDER BY rh.creado_en DESC LIMIT 100"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{reporte_id}")
def estado_reporte(reporte_id: str, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    _bootstrap_tabla(db)
    row = db.execute(text(
        "SELECT id::text, tipo, formato, estado, creado_en, completado_en, error FROM reporte_historial WHERE id=:id"
    ), {"id": reporte_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Reporte no encontrado")
    r = dict(row)
    r["descarga_url"] = f"/api/reportes/{reporte_id}/download" if r["estado"] == "listo" else None
    return r


@router.get("/{reporte_id}/download")
def descargar_reporte(reporte_id: str, db: Session = Depends(get_db),
                      current_user=Depends(get_current_user)):
    _bootstrap_tabla(db)
    row = db.execute(text(
        "SELECT tipo, formato, estado, ruta_archivo FROM reporte_historial WHERE id=:id"
    ), {"id": reporte_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Reporte no encontrado")
    if row["estado"] != "listo":
        raise HTTPException(409, f"Reporte en estado '{row['estado']}' — aún no disponible")
    ruta = Path(row["ruta_archivo"])
    if not ruta.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    ext = EXT.get(row["formato"], ".pdf")
    filename = f"MundoTec_{row['tipo']}_{reporte_id[:8]}{ext}"
    return FileResponse(str(ruta), media_type=MIME[row["formato"]], filename=filename)


def _bootstrap_tabla(db):
    """Crea reporte_historial si no existe (sin Alembic migration para simplicidad)."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS reporte_historial (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tipo TEXT NOT NULL,
            cliente_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            formato TEXT NOT NULL DEFAULT 'pdf',
            estado TEXT NOT NULL DEFAULT 'procesando',
            ruta_archivo TEXT,
            error TEXT,
            usuario_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            creado_en TIMESTAMPTZ DEFAULT now(),
            completado_en TIMESTAMPTZ
        )
    """))
    db.commit()
