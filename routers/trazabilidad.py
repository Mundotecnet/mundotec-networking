from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor
from services.trazabilidad import reconstruir_traza as _trazar

router = APIRouter(prefix="/trazabilidad", tags=["trazabilidad"])


# ── Trazabilidad ─────────────────────────────────────────────────────────────

@router.get("/endpoint/{endpoint_id}")
def trazar_endpoint(endpoint_id: str, db: Session = Depends(get_db),
                    current_user=Depends(get_current_user)):
    return _trazar(endpoint_id, db)


@router.get("/endpoint/{endpoint_id}/cache")
def traza_cache(endpoint_id: str, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    """Devuelve la última traza cacheada sin recalcular."""
    row = db.execute(text(
        "SELECT * FROM traza WHERE endpoint_id = :id ORDER BY calculado_en DESC LIMIT 1"
    ), {"id": endpoint_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Sin traza cacheada — use GET /trazabilidad/endpoint/{id}")
    return dict(row)


# ── Endpoints ─────────────────────────────────────────────────────────────────

class EndpointCreate(BaseModel):
    cliente_id: int
    sitio_id: Optional[str] = None
    tipo: str
    nombre: str
    hostname: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None
    faceplate_puerto_id: Optional[str] = None
    habitacion: Optional[str] = None
    extension_pbx: Optional[str] = None
    notas: Optional[str] = None


@router.get("/endpoints")
def listar_endpoints(cliente_id: Optional[int] = None, sitio_id: Optional[str] = None,
                     q: Optional[str] = None, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    sql = """
        SELECT e.*, c.name AS cliente_nombre, s.nombre AS sitio_nombre,
               e.ip::text AS ip, e.mac::text AS mac
        FROM endpoint e
        LEFT JOIN clients c ON c.id = e.cliente_id
        LEFT JOIN sitio s ON s.id = e.sitio_id
        WHERE 1=1
    """
    params = {}
    if cliente_id:
        sql += " AND e.cliente_id = :cid"
        params["cid"] = cliente_id
    if sitio_id:
        sql += " AND e.sitio_id = :sid"
        params["sid"] = sitio_id
    if q:
        sql += """ AND (lower(e.nombre) LIKE :q OR lower(e.hostname) LIKE :q
                    OR e.ip::text LIKE :q OR e.mac::text LIKE :q)"""
        params["q"] = f"%{q.lower()}%"
    sql += " ORDER BY c.name, e.nombre LIMIT 500"
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/endpoints/{endpoint_id}")
def detalle_endpoint(endpoint_id: str, db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT e.*, c.name AS cliente_nombre, s.nombre AS sitio_nombre,
               e.ip::text AS ip, e.mac::text AS mac
        FROM endpoint e
        LEFT JOIN clients c ON c.id = e.cliente_id
        LEFT JOIN sitio s ON s.id = e.sitio_id
        WHERE e.id = :id
    """), {"id": endpoint_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Endpoint no encontrado")
    return dict(row)


@router.post("/endpoints", status_code=201)
def crear_endpoint(data: EndpointCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO endpoint (id, cliente_id, sitio_id, tipo, nombre, hostname,
                              ip, mac, faceplate_puerto_id, habitacion, extension_pbx, notas)
        VALUES (:id, :cid, :sid, :tipo, :nom, :host,
                :ip, :mac, :face, :hab, :ext, :notas)
    """), {
        "id": nuevo_id, "cid": data.cliente_id, "sid": data.sitio_id,
        "tipo": data.tipo, "nom": data.nombre, "host": data.hostname,
        "ip": data.ip, "mac": data.mac, "face": data.faceplate_puerto_id,
        "hab": data.habitacion, "ext": data.extension_pbx, "notas": data.notas,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


# ── Cables ────────────────────────────────────────────────────────────────────

class CableCreate(BaseModel):
    codigo: str
    tipo: str
    extremo_a_puerto_id: str
    extremo_b_puerto_id: str
    longitud_m: Optional[float] = None
    color: Optional[str] = None
    ruta_fisica: Optional[str] = None
    notas: Optional[str] = None


@router.get("/cables")
def listar_cables(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("SELECT * FROM cable ORDER BY codigo")).mappings().all()
    return [dict(r) for r in rows]


@router.post("/cables", status_code=201)
def registrar_cable(data: CableCreate, db: Session = Depends(get_db),
                    current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO cable (id, codigo, tipo, extremo_a_puerto_id, extremo_b_puerto_id,
                           longitud_m, color, ruta_fisica, notas)
        VALUES (:id, :cod, :tipo, :a, :b, :lon, :col, :ruta, :notas)
    """), {
        "id": nuevo_id, "cod": data.codigo, "tipo": data.tipo,
        "a": data.extremo_a_puerto_id, "b": data.extremo_b_puerto_id,
        "lon": data.longitud_m, "col": data.color,
        "ruta": data.ruta_fisica, "notas": data.notas,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.delete("/cables/{cable_id}")
def eliminar_cable(cable_id: str, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM cable WHERE id = :id"), {"id": cable_id})
    db.commit()
    return {"ok": True}


# ── Jumpers ───────────────────────────────────────────────────────────────────

class JumperCreate(BaseModel):
    gabinete_id: str
    extremo_a_puerto_id: str
    extremo_b_puerto_id: str
    codigo: Optional[str] = None
    longitud_cm: Optional[int] = None
    color: Optional[str] = None
    tipo: Optional[str] = "utp"


@router.get("/jumpers")
def listar_jumpers(gabinete_id: Optional[str] = None, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    q = "SELECT * FROM jumper"
    params = {}
    if gabinete_id:
        q += " WHERE gabinete_id = :gid"
        params["gid"] = gabinete_id
    q += " ORDER BY codigo NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/jumpers", status_code=201)
def registrar_jumper(data: JumperCreate, db: Session = Depends(get_db),
                     current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO jumper (id, gabinete_id, codigo, longitud_cm, color, tipo,
                            extremo_a_puerto_id, extremo_b_puerto_id)
        VALUES (:id, :gid, :cod, :lon, :col, :tipo, :a, :b)
    """), {
        "id": nuevo_id, "gid": data.gabinete_id, "cod": data.codigo,
        "lon": data.longitud_cm, "col": data.color, "tipo": data.tipo,
        "a": data.extremo_a_puerto_id, "b": data.extremo_b_puerto_id,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


# ── Empalmes de fibra ─────────────────────────────────────────────────────────

class EmpalmeCreate(BaseModel):
    odf_origen_id: str
    odf_destino_id: str
    conector: Optional[str] = None
    hilos_totales: Optional[int] = None
    hilos_fusionados: Optional[int] = None
    atenuacion_db: Optional[float] = None
    fecha_fusion: Optional[str] = None


@router.get("/empalmes")
def listar_empalmes(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("SELECT * FROM empalme_fibra ORDER BY fecha_fusion DESC NULLS LAST")).mappings().all()
    return [dict(r) for r in rows]


@router.post("/empalmes", status_code=201)
def registrar_empalme(data: EmpalmeCreate, db: Session = Depends(get_db),
                      current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO empalme_fibra (id, odf_origen_id, odf_destino_id, conector,
                                   hilos_totales, hilos_fusionados, atenuacion_db, fecha_fusion)
        VALUES (:id, :orig, :dest, :con, :ht, :hf, :atten, :fecha)
    """), {
        "id": nuevo_id, "orig": data.odf_origen_id, "dest": data.odf_destino_id,
        "con": data.conector, "ht": data.hilos_totales, "hf": data.hilos_fusionados,
        "atten": data.atenuacion_db, "fecha": data.fecha_fusion,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


# ── Puertos terminales (lectura y creación básica) ────────────────────────────

class PuertoCreate(BaseModel):
    tipo: str
    patch_panel_id: Optional[str] = None
    equipo_id: Optional[str] = None
    faceplate_cuarto_id: Optional[str] = None
    numero: Optional[int] = None
    etiqueta_norm: Optional[str] = None   # auto-generada por trigger si es None
    etiqueta_display: Optional[str] = None
    notas: Optional[str] = None


@router.get("/puertos")
def listar_puertos(patch_panel_id: Optional[str] = None, equipo_id: Optional[str] = None,
                   db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = "SELECT * FROM puerto_terminal WHERE 1=1"
    params = {}
    if patch_panel_id:
        q += " AND patch_panel_id = :ppid"
        params["ppid"] = patch_panel_id
    if equipo_id:
        q += " AND equipo_id = :eqid"
        params["eqid"] = equipo_id
    q += " ORDER BY numero NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/puertos", status_code=201)
def crear_puerto(data: PuertoCreate, db: Session = Depends(get_db),
                 current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    # Si no viene etiqueta_norm, el trigger PG la auto-genera
    etq = data.etiqueta_norm or "PENDING"
    db.execute(text("""
        INSERT INTO puerto_terminal (id, tipo, patch_panel_id, equipo_id,
                                    faceplate_cuarto_id, numero, etiqueta_norm,
                                    etiqueta_display, notas)
        VALUES (:id, :tipo, :pp, :eq, :face, :num, :etq, :disp, :notas)
    """), {
        "id": nuevo_id, "tipo": data.tipo, "pp": data.patch_panel_id,
        "eq": data.equipo_id, "face": data.faceplate_cuarto_id,
        "num": data.numero, "etq": etq, "disp": data.etiqueta_display,
        "notas": data.notas,
    })
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}
