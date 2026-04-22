from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/fibra", tags=["fibra"])


class OdfCreate(BaseModel):
    gabinete_id: str
    codigo: str
    puertos_total: int
    categoria: Optional[str] = "SM"
    fabricante: Optional[str] = None
    modelo: Optional[str] = None


class OtdrCreate(BaseModel):
    empalme_id: Optional[str] = None
    odf_puerto_id: Optional[str] = None
    fecha_medicion: Optional[str] = None
    longitud_m: Optional[float] = None
    perdida_total_db: Optional[float] = None
    reflectancia_db: Optional[float] = None
    resultado: Optional[str] = "ok"
    notas: Optional[str] = None


@router.get("/odfs")
def listar_odfs(gabinete_id: Optional[str] = None, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    q = """
        SELECT pp.*, g.codigo AS gabinete_codigo, cu.nombre AS cuarto_nombre,
               e.nombre AS edificio_nombre, s.nombre AS sitio_nombre,
               count(pt.id) AS puertos_count
        FROM patch_panel pp JOIN gabinete g ON g.id = pp.gabinete_id
        JOIN cuarto cu ON cu.id = g.cuarto_id JOIN edificio e ON e.id = cu.edificio_id
        JOIN sitio s ON s.id = e.sitio_id
        LEFT JOIN puerto_terminal pt ON pt.patch_panel_id = pp.id
        WHERE pp.tipo = 'fibra'
    """
    params = {}
    if gabinete_id:
        q += " AND pp.gabinete_id = :gid"
        params["gid"] = gabinete_id
    q += " GROUP BY pp.id, g.codigo, cu.nombre, e.nombre, s.nombre ORDER BY s.nombre, pp.codigo"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/odfs/{odf_id}")
def detalle_odf(odf_id: str, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    pp = db.execute(text("""
        SELECT pp.*, g.codigo AS gabinete_codigo, cu.nombre AS cuarto_nombre
        FROM patch_panel pp JOIN gabinete g ON g.id = pp.gabinete_id
        JOIN cuarto cu ON cu.id = g.cuarto_id
        WHERE pp.id = :id AND pp.tipo = 'fibra'
    """), {"id": odf_id}).mappings().first()
    if not pp:
        raise HTTPException(404, "ODF no encontrado")
    puertos = db.execute(text("""
        SELECT pt.*, pt.etiqueta_norm, ef_out.id::text AS empalme_salida_id
        FROM puerto_terminal pt
        LEFT JOIN empalme_fibra ef_out ON ef_out.odf_origen_id = pt.id
        WHERE pt.patch_panel_id = :ppid ORDER BY pt.numero
    """), {"ppid": odf_id}).mappings().all()
    return {**dict(pp), "puertos": [dict(p) for p in puertos]}


@router.post("/odfs", status_code=201)
def crear_odf(data: OdfCreate, db: Session = Depends(get_db),
              current_user=Depends(require_editor)):
    odf_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO patch_panel (id, gabinete_id, codigo, tipo, categoria,
                                  puertos_total, fabricante, modelo)
        VALUES (:id, :gid, :cod, 'fibra', :cat, :total, :fab, :mod)
    """), {"id": odf_id, "gid": data.gabinete_id, "cod": data.codigo,
           "cat": data.categoria, "total": data.puertos_total,
           "fab": data.fabricante, "mod": data.modelo})
    for i in range(1, data.puertos_total + 1):
        pid = str(uuid.uuid4())
        etq = f"FO-1-A-A-A-{data.codigo}-{i:02d}"
        db.execute(text("""
            INSERT INTO puerto_terminal (id, tipo, patch_panel_id, numero, etiqueta_norm)
            VALUES (:id, 'fiber_odf_port', :pp, :num, :etq)
            ON CONFLICT (etiqueta_norm) DO NOTHING
        """), {"id": pid, "pp": odf_id, "num": i, "etq": etq})
    db.commit()
    return {"id": odf_id, "puertos_creados": data.puertos_total, **data.model_dump()}


@router.get("/ruta")
def ruta_optica(odf_a: str, odf_b: str, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    empalmes = db.execute(text("""
        WITH RECURSIVE ruta AS (
            SELECT ef.id::text, ef.odf_origen_id::text, ef.odf_destino_id::text,
                   ef.atenuacion_db, 1 AS nivel, ARRAY[ef.id::text] AS visitados
            FROM empalme_fibra ef
            WHERE ef.odf_origen_id = :a OR ef.odf_destino_id = :a
            UNION ALL
            SELECT ef.id::text, ef.odf_origen_id::text, ef.odf_destino_id::text,
                   ef.atenuacion_db, r.nivel + 1, r.visitados || ef.id::text
            FROM empalme_fibra ef, ruta r
            WHERE (ef.odf_origen_id::text = r.odf_destino_id OR ef.odf_destino_id::text = r.odf_origen_id)
              AND NOT (ef.id::text = ANY(r.visitados)) AND r.nivel < 10
        )
        SELECT * FROM ruta ORDER BY nivel LIMIT 20
    """), {"a": odf_a}).mappings().all()
    return {"odf_a": odf_a, "odf_b": odf_b, "empalmes": [dict(e) for e in empalmes],
            "nota": "Ruta aproximada — validar con documentación física"}


@router.get("/otdr")
def listar_otdr(empalme_id: Optional[str] = None, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    q = "SELECT * FROM medicion_otdr WHERE 1=1"
    params = {}
    if empalme_id:
        q += " AND empalme_id = :eid"
        params["eid"] = empalme_id
    q += " ORDER BY fecha_medicion DESC NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/otdr", status_code=201)
def registrar_otdr(data: OtdrCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    alerta = None
    if data.perdida_total_db and data.perdida_total_db > 3.0:
        alerta = f"Pérdida {data.perdida_total_db} dB supera presupuesto óptico (3 dB)"
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO medicion_otdr (id, empalme_id, odf_puerto_id, fecha_medicion,
                                    longitud_m, perdida_total_db, reflectancia_db, resultado, notas)
        VALUES (:id,:emp,:odf,:fecha,:lon,:perdida,:refl,:res,:notas)
    """), {"id": nuevo_id, "emp": data.empalme_id, "odf": data.odf_puerto_id,
           "fecha": data.fecha_medicion, "lon": data.longitud_m,
           "perdida": data.perdida_total_db, "refl": data.reflectancia_db,
           "res": data.resultado, "notas": data.notas})
    db.commit()
    return {"id": nuevo_id, "alerta": alerta, **data.model_dump()}
