from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor

router = APIRouter(prefix="/ipam", tags=["ipam"])


class VlanCreate(BaseModel):
    cliente_id: int
    sitio_id: Optional[str] = None
    vlan_id: int
    nombre: str
    descripcion: Optional[str] = None
    color_hex: Optional[str] = None


class SubredCreate(BaseModel):
    sitio_id: str
    vlan_id: Optional[str] = None
    cidr: str
    gateway: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = None


class AsignacionCreate(BaseModel):
    subred_id: str
    ip: str
    endpoint_id: Optional[str] = None
    equipo_id: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = "estatica"


class WanCreate(BaseModel):
    sitio_id: str
    isp: str
    producto: Optional[str] = None
    ip_publica: Optional[str] = None
    gateway: Optional[str] = None
    ancho_banda_mbps: Optional[int] = None
    contrato: Optional[str] = None
    observaciones: Optional[str] = None


@router.get("/vlans")
def listar_vlans(cliente_id: Optional[int] = None, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    q = """
        SELECT v.*, c.name AS cliente_nombre, count(s.id) AS subredes_count
        FROM vlan v JOIN clients c ON c.id = v.cliente_id
        LEFT JOIN subred s ON s.vlan_id = v.id WHERE 1=1
    """
    params = {}
    if cliente_id:
        q += " AND v.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " GROUP BY v.id, c.name ORDER BY c.name, v.vlan_id"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/vlans", status_code=201)
def crear_vlan(data: VlanCreate, db: Session = Depends(get_db),
               current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO vlan (id, cliente_id, sitio_id, vlan_id, nombre, descripcion, color_hex)
        VALUES (:id, :cid, :sid, :vid, :nom, :desc, :col)
    """), {"id": nuevo_id, "cid": data.cliente_id, "sid": data.sitio_id,
           "vid": data.vlan_id, "nom": data.nombre, "desc": data.descripcion,
           "col": data.color_hex})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.delete("/vlans/{vlan_id}")
def eliminar_vlan(vlan_id: str, db: Session = Depends(get_db),
                  current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM vlan WHERE id = :id"), {"id": vlan_id})
    db.commit()
    return {"ok": True}


@router.get("/subredes")
def listar_subredes(sitio_id: Optional[str] = None, cliente_id: Optional[int] = None,
                    db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = """
        SELECT sub.*, sub.cidr::text AS cidr_text, sub.gateway::text AS gateway_text,
               s.nombre AS sitio_nombre, c.name AS cliente_nombre,
               v.nombre AS vlan_nombre, v.vlan_id AS vlan_num,
               count(a.id) AS asignaciones_count
        FROM subred sub JOIN sitio s ON s.id = sub.sitio_id
        JOIN clients c ON c.id = s.cliente_id
        LEFT JOIN vlan v ON v.id = sub.vlan_id
        LEFT JOIN asignacion_ip a ON a.subred_id = sub.id WHERE 1=1
    """
    params = {}
    if sitio_id:
        q += " AND sub.sitio_id = :sid"
        params["sid"] = sitio_id
    if cliente_id:
        q += " AND s.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " GROUP BY sub.id, s.nombre, c.name, v.nombre, v.vlan_id ORDER BY sub.cidr"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/subredes/{subred_id}/mapa")
def mapa_subred(subred_id: str, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    sub = db.execute(text("""
        SELECT id::text, cidr::text, gateway::text, descripcion,
               host(network(cidr))::text AS red,
               broadcast(cidr)::text AS broadcast,
               masklen(cidr) AS prefixlen
        FROM subred WHERE id = :id
    """), {"id": subred_id}).mappings().first()
    if not sub:
        raise HTTPException(404, "Subred no encontrada")

    asignaciones = db.execute(text("""
        SELECT a.ip::text AS ip, a.tipo, a.descripcion, a.activa,
               e.nombre AS endpoint_nombre, eq.nombre AS equipo_nombre
        FROM asignacion_ip a
        LEFT JOIN endpoint e ON e.id = a.endpoint_id
        LEFT JOIN equipo eq ON eq.id = a.equipo_id
        WHERE a.subred_id = :sid ORDER BY a.ip
    """), {"sid": subred_id}).mappings().all()

    return {"subred": dict(sub), "asignaciones": [dict(a) for a in asignaciones],
            "total_asignadas": len(asignaciones)}


@router.post("/subredes", status_code=201)
def crear_subred(data: SubredCreate, db: Session = Depends(get_db),
                 current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO subred (id, sitio_id, vlan_id, cidr, gateway, descripcion, tipo)
        VALUES (:id, :sid, :vid, :cidr, :gw, :desc, :tipo)
    """), {"id": nuevo_id, "sid": data.sitio_id, "vid": data.vlan_id,
           "cidr": data.cidr, "gw": data.gateway, "desc": data.descripcion,
           "tipo": data.tipo})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.post("/asignaciones", status_code=201)
def reservar_ip(data: AsignacionCreate, db: Session = Depends(get_db),
                current_user=Depends(require_editor)):
    existe = db.execute(text(
        "SELECT id FROM asignacion_ip WHERE subred_id=:sid AND ip=:ip AND activa=true"
    ), {"sid": data.subred_id, "ip": data.ip}).scalar()
    if existe:
        raise HTTPException(409, f"IP {data.ip} ya está asignada en esta subred")
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO asignacion_ip (id, subred_id, ip, endpoint_id, equipo_id, descripcion, tipo)
        VALUES (:id, :sid, :ip, :eid, :eqid, :desc, :tipo)
    """), {"id": nuevo_id, "sid": data.subred_id, "ip": data.ip,
           "eid": data.endpoint_id, "eqid": data.equipo_id,
           "desc": data.descripcion, "tipo": data.tipo})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.delete("/asignaciones/{asig_id}")
def liberar_ip(asig_id: str, db: Session = Depends(get_db),
               current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM asignacion_ip WHERE id=:id"), {"id": asig_id})
    db.commit()
    return {"ok": True}


@router.get("/buscar-ip")
def buscar_ip(q: str, db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT a.ip::text AS ip, a.tipo, a.descripcion,
               sub.cidr::text AS subred, s.nombre AS sitio, c.name AS cliente,
               e.nombre AS endpoint_nombre, e.id::text AS endpoint_id,
               eq.nombre AS equipo_nombre, eq.id::text AS equipo_id
        FROM asignacion_ip a JOIN subred sub ON sub.id = a.subred_id
        JOIN sitio s ON s.id = sub.sitio_id JOIN clients c ON c.id = s.cliente_id
        LEFT JOIN endpoint e ON e.id = a.endpoint_id
        LEFT JOIN equipo eq ON eq.id = a.equipo_id
        WHERE a.ip::text LIKE :q ORDER BY a.ip LIMIT 50
    """), {"q": f"%{q}%"}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/wan")
def listar_wan(sitio_id: Optional[str] = None, db: Session = Depends(get_db),
               current_user=Depends(get_current_user)):
    q = """
        SELECT w.*, w.ip_publica::text AS ip_publica_text, w.gateway::text AS gateway_text,
               s.nombre AS sitio_nombre, c.name AS cliente_nombre
        FROM wan w JOIN sitio s ON s.id = w.sitio_id
        JOIN clients c ON c.id = s.cliente_id WHERE 1=1
    """
    params = {}
    if sitio_id:
        q += " AND w.sitio_id = :sid"
        params["sid"] = sitio_id
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/wan", status_code=201)
def registrar_wan(data: WanCreate, db: Session = Depends(get_db),
                  current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO wan (id, sitio_id, isp, producto, ip_publica, gateway,
                         ancho_banda_mbps, contrato, observaciones)
        VALUES (:id,:sid,:isp,:prod,:ip,:gw,:bw,:cont,:obs)
    """), {"id": nuevo_id, "sid": data.sitio_id, "isp": data.isp,
           "prod": data.producto, "ip": data.ip_publica, "gw": data.gateway,
           "bw": data.ancho_banda_mbps, "cont": data.contrato, "obs": data.observaciones})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}
