"""
Servicio de trazabilidad end-to-end.
Reconstruye la cadena de hops desde un endpoint hasta el uplink del switch core,
siguiendo la secuencia:
  endpoint → faceplate → cable horizontal → patch_panel_port →
  jumper → switch_port → (uplink) → ...
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import datetime

MAX_HOPS = 20


def reconstruir_traza(endpoint_id: str, db: Session) -> dict:
    """
    Devuelve la traza hop-by-hop para un endpoint.
    Guarda/actualiza el resultado en la tabla `traza` para cache.
    """
    ep = db.execute(text("""
        SELECT e.id, e.nombre, e.tipo, e.ip::text AS ip, e.mac::text AS mac,
               e.hostname, e.faceplate_puerto_id::text AS faceplate_puerto_id,
               e.habitacion, s.nombre AS sitio_nombre, c.name AS cliente_nombre
        FROM endpoint e
        LEFT JOIN sitio s ON s.id = e.sitio_id
        LEFT JOIN clients c ON c.id = e.cliente_id
        WHERE e.id = :id
    """), {"id": endpoint_id}).mappings().first()

    if not ep:
        return {"error": "Endpoint no encontrado", "endpoint_id": endpoint_id}

    hops = []
    estado_global = "verde"

    # ── Hop 0: el endpoint mismo ──────────────────────────────────────────
    hops.append({
        "orden": 0,
        "tipo": "endpoint",
        "label": ep["nombre"],
        "detalle": f"{ep['tipo']} — IP: {ep['ip'] or '—'} MAC: {ep['mac'] or '—'}",
        "estado": "verde",
        "ref_id": str(ep["id"]),
        "ref_tipo": "endpoint",
    })

    if not ep["faceplate_puerto_id"]:
        return _armar_respuesta(endpoint_id, ep, hops, "amarillo",
                                "Sin faceplate asignado", db)

    # ── Seguir la cadena de conexiones ─────────────────────────────────────
    puerto_actual_id = ep["faceplate_puerto_id"]
    visitados = set()

    for _ in range(MAX_HOPS):
        if puerto_actual_id in visitados:
            hops.append(_hop_error("Bucle detectado en la traza", puerto_actual_id))
            estado_global = "rojo"
            break
        visitados.add(puerto_actual_id)

        puerto = _get_puerto(puerto_actual_id, db)
        if not puerto:
            break

        hop = _puerto_a_hop(len(hops), puerto)
        hops.append(hop)

        if hop["estado"] == "rojo":
            estado_global = "rojo"

        # Buscar el cable/jumper que sale de este puerto
        conexion = _buscar_conexion(puerto_actual_id, db)
        if not conexion:
            break

        hops.append({
            "orden": len(hops),
            "tipo": conexion["tipo_conexion"],
            "label": conexion["codigo"] or f"{conexion['tipo_conexion'].capitalize()} sin código",
            "detalle": _detalle_conexion(conexion),
            "estado": "verde",
            "ref_id": str(conexion["id"]),
            "ref_tipo": conexion["tipo_conexion"],
        })

        # El extremo opuesto es el siguiente puerto
        if str(conexion["extremo_a_puerto_id"]) == puerto_actual_id:
            puerto_actual_id = str(conexion["extremo_b_puerto_id"])
        else:
            puerto_actual_id = str(conexion["extremo_a_puerto_id"])

    return _armar_respuesta(endpoint_id, ep, hops, estado_global, None, db)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_puerto(puerto_id: str, db: Session) -> Optional[dict]:
    row = db.execute(text("""
        SELECT
            pt.id, pt.tipo, pt.etiqueta_norm, pt.etiqueta_display,
            pt.estado_admin, pt.numero, pt.notas,
            pp.codigo AS panel_codigo, pp.tipo AS panel_tipo,
            g.codigo AS gabinete_codigo, g.nombre AS gabinete_nombre,
            cu.nombre AS cuarto_nombre,
            eq.nombre AS equipo_nombre, eq.tipo AS equipo_tipo,
            eq.ip_gestion::text AS equipo_ip
        FROM puerto_terminal pt
        LEFT JOIN patch_panel pp ON pp.id = pt.patch_panel_id
        LEFT JOIN gabinete g ON g.id = COALESCE(pp.gabinete_id, eq.gabinete_id)
        LEFT JOIN cuarto cu ON cu.id = g.cuarto_id
        LEFT JOIN equipo eq ON eq.id = pt.equipo_id
        WHERE pt.id = :id
    """), {"id": puerto_id}).mappings().first()
    return dict(row) if row else None


def _puerto_a_hop(orden: int, p: dict) -> dict:
    tipo = p["tipo"]
    etiqueta = p["etiqueta_norm"] or p["etiqueta_display"] or "—"
    estado_admin = p["estado_admin"]

    if tipo == "faceplate":
        label = f"Faceplate {etiqueta}"
        detalle = f"Cuarto: {p['cuarto_nombre'] or '—'}"
    elif tipo == "patch_panel_port":
        label = f"Panel {etiqueta}"
        detalle = f"Gabinete: {p['gabinete_nombre'] or p['gabinete_codigo'] or '—'}"
    elif tipo in ("switch_port", "router_port", "ont_port", "sfp_port"):
        label = f"{p['equipo_nombre'] or '—'} / {etiqueta}"
        detalle = f"IP: {p['equipo_ip'] or '—'} | Estado: {estado_admin or 'desconocido'}"
    elif tipo == "fiber_odf_port":
        label = f"ODF {etiqueta}"
        detalle = f"Gabinete: {p['gabinete_codigo'] or '—'}"
    else:
        label = etiqueta
        detalle = tipo

    # Semáforo
    if estado_admin in ("down", "shut"):
        estado = "rojo"
    elif estado_admin is None:
        estado = "verde"
    else:
        estado = "verde"

    return {
        "orden": orden,
        "tipo": tipo,
        "label": label,
        "detalle": detalle,
        "estado": estado,
        "ref_id": str(p["id"]),
        "ref_tipo": "puerto_terminal",
        "etiqueta": etiqueta,
    }


def _buscar_conexion(puerto_id: str, db: Session) -> Optional[dict]:
    """Busca cable o jumper que tenga este puerto en alguno de sus extremos."""
    row = db.execute(text("""
        SELECT id, codigo, 'cable' AS tipo_conexion,
               extremo_a_puerto_id::text, extremo_b_puerto_id::text,
               tipo AS subtipo, longitud_m::text AS longitud, NULL::int AS longitud_cm
        FROM cable
        WHERE extremo_a_puerto_id = :pid OR extremo_b_puerto_id = :pid
        UNION ALL
        SELECT id, codigo, 'jumper' AS tipo_conexion,
               extremo_a_puerto_id::text, extremo_b_puerto_id::text,
               tipo AS subtipo, NULL, longitud_cm
        FROM jumper
        WHERE extremo_a_puerto_id = :pid OR extremo_b_puerto_id = :pid
        LIMIT 1
    """), {"pid": puerto_id}).mappings().first()
    return dict(row) if row else None


def _detalle_conexion(c: dict) -> str:
    if c["tipo_conexion"] == "cable":
        return f"{c['subtipo'] or 'cable'} — {c['longitud'] or '?'} m"
    return f"Jumper {c['subtipo'] or 'utp'} — {c['longitud_cm'] or '?'} cm"


def _hop_error(msg: str, ref_id: str) -> dict:
    return {
        "orden": 99,
        "tipo": "error",
        "label": msg,
        "detalle": "",
        "estado": "rojo",
        "ref_id": ref_id,
        "ref_tipo": "error",
    }


def _armar_respuesta(endpoint_id: str, ep: dict, hops: list,
                     estado: str, advertencia: Optional[str], db: Session) -> dict:
    resumen = " → ".join(h["label"] for h in hops[:6])
    if len(hops) > 6:
        resumen += " → ..."

    # Guardar/actualizar cache en tabla traza
    try:
        import json
        db.execute(text("""
            INSERT INTO traza (endpoint_id, hops, resumen, hops_count, calculado_en)
            VALUES (:eid, :hops::jsonb, :res, :cnt, now())
            ON CONFLICT (endpoint_id) DO UPDATE
              SET hops = EXCLUDED.hops,
                  resumen = EXCLUDED.resumen,
                  hops_count = EXCLUDED.hops_count,
                  calculado_en = now()
        """), {
            "eid": endpoint_id,
            "hops": json.dumps(hops),
            "res": resumen,
            "cnt": len(hops),
        })
        db.commit()
    except Exception:
        db.rollback()

    return {
        "endpoint_id": endpoint_id,
        "endpoint_nombre": ep["nombre"],
        "cliente": ep["cliente_nombre"],
        "sitio": ep["sitio_nombre"],
        "estado_global": estado,
        "advertencia": advertencia,
        "hops_count": len(hops),
        "hops": hops,
        "resumen": resumen,
        "calculado_en": datetime.datetime.utcnow().isoformat(),
    }
