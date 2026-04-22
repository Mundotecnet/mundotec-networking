from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from auth.jwt import get_current_user, require_editor, require_admin
from services.crypto import encrypt, decrypt
from services.audit import log as audit_log

router = APIRouter(prefix="/credenciales", tags=["credenciales"])


class CredencialCreate(BaseModel):
    cliente_id: int
    equipo_id: Optional[str] = None
    servicio: str
    usuario: Optional[str] = None
    password: Optional[str] = None
    url: Optional[str] = None
    notas: Optional[str] = None


class LicenciaCreate(BaseModel):
    cliente_id: int
    producto: str
    tipo: Optional[str] = None
    clave: Optional[str] = None
    fecha_activacion: Optional[str] = None
    fecha_vencimiento: Optional[str] = None
    endpoint_id: Optional[str] = None
    activaciones_max: Optional[int] = None
    proveedor: Optional[str] = None
    notas: Optional[str] = None


class TenantCreate(BaseModel):
    cliente_id: int
    proveedor: Optional[str] = None
    dominio: str
    admin_user: Optional[str] = None
    telefono_recup: Optional[str] = None
    email_recup: Optional[str] = None
    notas: Optional[str] = None


class CuentaCreate(BaseModel):
    tenant_id: str
    email: str
    credencial_id: Optional[str] = None
    activa: Optional[bool] = True


@router.get("")
def listar_credenciales(cliente_id: Optional[int] = None,
                        db: Session = Depends(get_db),
                        current_user=Depends(get_current_user)):
    q = """
        SELECT cr.id::text, cr.cliente_id, cr.servicio, cr.usuario, cr.url,
               cr.notas, cr.creado_en, c.name AS cliente_nombre,
               eq.nombre AS equipo_nombre
        FROM credencial cr JOIN clients c ON c.id = cr.cliente_id
        LEFT JOIN equipo eq ON eq.id = cr.equipo_id WHERE 1=1
    """
    params = {}
    if cliente_id:
        q += " AND cr.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " ORDER BY c.name, cr.servicio"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{cred_id}/reveal")
def revelar_password(cred_id: str, db: Session = Depends(get_db),
                     current_user=Depends(require_editor)):
    row = db.execute(text("""
        SELECT cr.password_cifrado, cr.servicio, cr.usuario, c.name AS cliente
        FROM credencial cr JOIN clients c ON c.id = cr.cliente_id WHERE cr.id = :id
    """), {"id": cred_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Credencial no encontrada")
    password = None
    if row["password_cifrado"]:
        try:
            password = decrypt(row["password_cifrado"].decode() if isinstance(row["password_cifrado"], bytes) else row["password_cifrado"])
        except Exception:
            raise HTTPException(500, "Error al descifrar — verifique FERNET_KEY")
    audit_log(db, current_user, "reveal", "credencial", cred_id,
              label=f"{row['servicio']} ({row['cliente']})")
    return {"id": cred_id, "servicio": row["servicio"], "usuario": row["usuario"], "password": password}


@router.post("", status_code=201)
def crear_credencial(data: CredencialCreate, db: Session = Depends(get_db),
                     current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    pw_cifrado = None
    if data.password:
        pw_cifrado = encrypt(data.password)
    db.execute(text("""
        INSERT INTO credencial (id, cliente_id, equipo_id, servicio, usuario,
                                password_cifrado, url, notas, creado_por)
        VALUES (:id, :cid, :eqid, :srv, :usr, :pw, :url, :notas, :por)
    """), {"id": nuevo_id, "cid": data.cliente_id, "eqid": data.equipo_id,
           "srv": data.servicio, "usr": data.usuario, "pw": pw_cifrado,
           "url": data.url, "notas": data.notas, "por": current_user.id})
    db.commit()
    return {"id": nuevo_id, "servicio": data.servicio, "cliente_id": data.cliente_id}


@router.delete("/{cred_id}")
def eliminar_credencial(cred_id: str, db: Session = Depends(get_db),
                        current_user=Depends(require_admin)):
    db.execute(text("DELETE FROM credencial WHERE id = :id"), {"id": cred_id})
    db.commit()
    return {"ok": True}


@router.get("/licencias")
def listar_licencias(cliente_id: Optional[int] = None,
                     vence_en_dias: Optional[int] = None,
                     db: Session = Depends(get_db),
                     current_user=Depends(get_current_user)):
    q = """
        SELECT l.*, c.name AS cliente_nombre,
               CASE WHEN l.fecha_vencimiento IS NULL THEN 'sin_fecha'
                    WHEN l.fecha_vencimiento < CURRENT_DATE THEN 'vencida'
                    WHEN l.fecha_vencimiento <= CURRENT_DATE + INTERVAL '30 days' THEN 'por_vencer'
                    ELSE 'vigente' END AS estado,
               (l.fecha_vencimiento - CURRENT_DATE) AS dias_restantes
        FROM licencia l JOIN clients c ON c.id = l.cliente_id WHERE 1=1
    """
    params = {}
    if cliente_id:
        q += " AND l.cliente_id = :cid"
        params["cid"] = cliente_id
    if vence_en_dias:
        q += " AND l.fecha_vencimiento <= CURRENT_DATE + :dias * INTERVAL '1 day'"
        params["dias"] = vence_en_dias
    q += " ORDER BY l.fecha_vencimiento NULLS LAST"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/licencias", status_code=201)
def crear_licencia(data: LicenciaCreate, db: Session = Depends(get_db),
                   current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO licencia (id, cliente_id, producto, tipo, clave, fecha_activacion,
                               fecha_vencimiento, endpoint_id, activaciones_max, proveedor, notas)
        VALUES (:id,:cid,:prod,:tipo,:clave,:act,:venc,:epid,:maxact,:prov,:notas)
    """), {"id": nuevo_id, "cid": data.cliente_id, "prod": data.producto,
           "tipo": data.tipo, "clave": data.clave, "act": data.fecha_activacion,
           "venc": data.fecha_vencimiento, "epid": data.endpoint_id,
           "maxact": data.activaciones_max, "prov": data.proveedor, "notas": data.notas})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.delete("/licencias/{lic_id}")
def eliminar_licencia(lic_id: str, db: Session = Depends(get_db),
                      current_user=Depends(require_editor)):
    db.execute(text("DELETE FROM licencia WHERE id = :id"), {"id": lic_id})
    db.commit()
    return {"ok": True}


@router.get("/tenants")
def listar_tenants(cliente_id: Optional[int] = None,
                   db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    q = """
        SELECT t.*, c.name AS cliente_nombre, count(ct.id) AS cuentas_count
        FROM tenant_correo t JOIN clients c ON c.id = t.cliente_id
        LEFT JOIN cuenta_correo ct ON ct.tenant_id = t.id WHERE 1=1
    """
    params = {}
    if cliente_id:
        q += " AND t.cliente_id = :cid"
        params["cid"] = cliente_id
    q += " GROUP BY t.id, c.name ORDER BY c.name, t.dominio"
    rows = db.execute(text(q), params).mappings().all()
    return [dict(r) for r in rows]


@router.post("/tenants", status_code=201)
def crear_tenant(data: TenantCreate, db: Session = Depends(get_db),
                 current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO tenant_correo (id, cliente_id, proveedor, dominio,
                                    admin_user, telefono_recup, email_recup, notas)
        VALUES (:id,:cid,:prov,:dom,:adm,:tel,:email,:notas)
    """), {"id": nuevo_id, "cid": data.cliente_id, "prov": data.proveedor,
           "dom": data.dominio, "adm": data.admin_user, "tel": data.telefono_recup,
           "email": data.email_recup, "notas": data.notas})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}


@router.get("/tenants/{tenant_id}/cuentas")
def cuentas_tenant(tenant_id: str, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT ct.*, cr.servicio AS cred_servicio FROM cuenta_correo ct
        LEFT JOIN credencial cr ON cr.id = ct.credencial_id
        WHERE ct.tenant_id = :tid ORDER BY ct.email
    """), {"tid": tenant_id}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/tenants/{tenant_id}/cuentas", status_code=201)
def crear_cuenta(tenant_id: str, data: CuentaCreate,
                 db: Session = Depends(get_db),
                 current_user=Depends(require_editor)):
    nuevo_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO cuenta_correo (id, tenant_id, email, credencial_id, activa)
        VALUES (:id,:tid,:email,:crid,:act)
    """), {"id": nuevo_id, "tid": tenant_id, "email": data.email,
           "crid": data.credencial_id, "act": data.activa})
    db.commit()
    return {"id": nuevo_id, **data.model_dump()}
