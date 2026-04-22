"""
Búsqueda universal — motor unificado para el ⌘K de la SPA.
Busca en: endpoints, equipos, sitios, cuartos, cables, patch_ports (legacy), devices (legacy).
Devuelve resultados agrupados por tipo con link de navegación.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Any


def buscar(q: str, db: Session, limite_por_tipo: int = 10) -> dict[str, list[dict]]:
    """
    Búsqueda unificada. q puede ser: nombre parcial, IP, MAC, hostname, serial, código.
    Retorna resultados agrupados por tipo.
    """
    q = q.strip()
    if len(q) < 2:
        return {}

    like = f"%{q.lower()}%"
    resultados: dict[str, list[dict]] = {}

    # ── Endpoints (nuevo schema) ──────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT e.id::text, e.nombre, e.tipo, e.ip::text AS ip, e.mac::text AS mac,
               e.hostname, e.habitacion,
               c.name AS cliente, s.nombre AS sitio
        FROM endpoint e
        LEFT JOIN clients c ON c.id = e.cliente_id
        LEFT JOIN sitio s ON s.id = e.sitio_id
        WHERE lower(e.nombre) LIKE :q
           OR lower(e.hostname) LIKE :q
           OR e.ip::text LIKE :q
           OR e.mac::text ILIKE :q
           OR lower(e.habitacion) LIKE :q
        ORDER BY e.nombre
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["endpoint"] = [
            {
                "id": r["id"], "tipo": "endpoint",
                "label": r["nombre"],
                "sub": f"{r['tipo']} · {r['ip'] or r['mac'] or r['hostname'] or '—'}",
                "badge": r["cliente"] or "",
                "sitio": r["sitio"] or "",
                "nav": f"trazabilidad",
                "nav_id": r["id"],
            }
            for r in rows
        ]

    # ── Equipos (nuevo schema) ────────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT eq.id::text, eq.nombre, eq.tipo, eq.ip_gestion::text AS ip,
               eq.mac::text AS mac, eq.hostname, eq.serie,
               c.name AS cliente, s.nombre AS sitio
        FROM equipo eq
        LEFT JOIN clients c ON c.id = eq.cliente_id
        LEFT JOIN sitio s ON s.id = eq.sitio_id
        WHERE lower(eq.nombre) LIKE :q
           OR lower(eq.hostname) LIKE :q
           OR eq.ip_gestion::text LIKE :q
           OR eq.mac::text ILIKE :q
           OR lower(eq.serie) LIKE :q
        ORDER BY eq.nombre
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["equipo"] = [
            {
                "id": r["id"], "tipo": "equipo",
                "label": r["nombre"],
                "sub": f"{r['tipo']} · {r['ip'] or r['mac'] or '—'}",
                "badge": r["cliente"] or "",
                "sitio": r["sitio"] or "",
                "nav": "clients",
                "nav_id": r["id"],
            }
            for r in rows
        ]

    # ── Sitios ────────────────────────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT s.id::text, s.nombre, s.direccion, c.name AS cliente
        FROM sitio s
        JOIN clients c ON c.id = s.cliente_id
        WHERE lower(s.nombre) LIKE :q
           OR lower(s.direccion) LIKE :q
           OR lower(c.name) LIKE :q
        ORDER BY c.name, s.nombre
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["sitio"] = [
            {
                "id": r["id"], "tipo": "sitio",
                "label": r["nombre"],
                "sub": r["direccion"] or "",
                "badge": r["cliente"],
                "nav": "sitios",
                "nav_id": r["id"],
            }
            for r in rows
        ]

    # ── Cuartos ───────────────────────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT cu.id::text, cu.nombre, cu.codigo, cu.piso,
               e.nombre AS edificio, s.nombre AS sitio, c.name AS cliente
        FROM cuarto cu
        JOIN edificio e ON e.id = cu.edificio_id
        JOIN sitio s ON s.id = e.sitio_id
        JOIN clients c ON c.id = s.cliente_id
        WHERE lower(cu.nombre) LIKE :q
           OR lower(cu.codigo) LIKE :q
        ORDER BY cu.nombre
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["cuarto"] = [
            {
                "id": r["id"], "tipo": "cuarto",
                "label": r["nombre"],
                "sub": f"Piso {r['piso']} · {r['edificio']}",
                "badge": r["cliente"],
                "sitio": r["sitio"],
                "nav": "sitios",
                "nav_id": r["id"],
            }
            for r in rows
        ]

    # ── Cables (por código) ───────────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT id::text, codigo, tipo, longitud_m::text AS longitud
        FROM cable
        WHERE lower(codigo) LIKE :q
        ORDER BY codigo
        LIMIT :lim
    """), {"q": like, "lim": 5}).mappings().all()

    if rows:
        resultados["cable"] = [
            {
                "id": r["id"], "tipo": "cable",
                "label": r["codigo"],
                "sub": f"{r['tipo']} · {r['longitud'] or '?'} m",
                "badge": "",
                "nav": "trazabilidad",
                "nav_id": r["id"],
            }
            for r in rows
        ]

    # ── Puertos legacy (patch_ports) ──────────────────────────────────────────
    rows = db.execute(text("""
        SELECT pp2.id, pp2.label, pp2.node_mac AS mac, pp2.node_ip AS ip,
               pp2.node_description AS detalle,
               r.name AS cuarto, c.name AS cliente, c.id AS client_id
        FROM patch_ports pp2
        JOIN patch_panels pp ON pp.id = pp2.patch_panel_id
        JOIN rooms r ON r.id = pp.room_id
        JOIN clients c ON c.id = r.client_id
        WHERE lower(pp2.label) ILIKE :q
           OR lower(pp2.node_mac) ILIKE :q
           OR lower(pp2.node_ip) ILIKE :q
           OR lower(pp2.node_description) ILIKE :q
        ORDER BY pp2.label
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["patch_port"] = [
            {
                "id": str(r["id"]), "tipo": "patch_port",
                "label": r["label"] or "Puerto sin etiqueta",
                "sub": f"{r['detalle'] or ''} · {r['ip'] or r['mac'] or '—'}",
                "badge": r["cliente"],
                "sitio": r["cuarto"],
                "nav": "clients",
                "nav_id": str(r["client_id"]),
            }
            for r in rows
        ]

    # ── Equipos legacy (devices) ──────────────────────────────────────────────
    rows = db.execute(text("""
        SELECT d.id, d.name, d.device_type, d.ip, d.mac, d.hostname,
               r.name AS cuarto, c.name AS cliente, c.id AS client_id
        FROM devices d
        JOIN rooms r ON r.id = d.room_id
        JOIN clients c ON c.id = r.client_id
        WHERE lower(d.name) LIKE :q
           OR lower(d.mac) ILIKE :q
           OR lower(d.ip) LIKE :q
           OR lower(d.hostname) LIKE :q
        ORDER BY d.name
        LIMIT :lim
    """), {"q": like, "lim": limite_por_tipo}).mappings().all()

    if rows:
        resultados["device"] = [
            {
                "id": str(r["id"]), "tipo": "device",
                "label": r["name"],
                "sub": f"{r['device_type']} · {r['ip'] or r['mac'] or '—'}",
                "badge": r["cliente"],
                "sitio": r["cuarto"],
                "nav": "clients",
                "nav_id": str(r["client_id"]),
            }
            for r in rows
        ]

    return resultados
