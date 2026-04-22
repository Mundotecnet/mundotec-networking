"""Construye contexto para el inventario XLSX."""
from sqlalchemy import text


def construir(db, cliente_id, **kwargs) -> dict:
    cli = db.execute(text("SELECT name FROM clients WHERE id=:id"), {"id": cliente_id}).mappings().first()
    nombre = cli["name"] if cli else "—"

    equipos = db.execute(text("""
        SELECT eq.nombre, eq.tipo, eq.marca, eq.modelo, eq.ip_gestion, eq.codigo_rack,
               '' AS estado,
               s.nombre AS sitio_nombre, cu.nombre AS cuarto_nombre
        FROM equipo eq LEFT JOIN sitio s ON s.id=eq.sitio_id
        LEFT JOIN cuarto cu ON cu.id=eq.cuarto_id
        WHERE eq.cliente_id=:cid ORDER BY s.nombre, eq.nombre
    """), {"cid": cliente_id}).mappings().all()

    endpoints = db.execute(text("""
        SELECT ep.nombre, ep.tipo, ep.ip, ep.mac, ep.habitacion,
               s.nombre AS sitio_nombre
        FROM endpoint ep LEFT JOIN sitio s ON s.id=ep.sitio_id
        WHERE ep.cliente_id=:cid ORDER BY ep.nombre
    """), {"cid": cliente_id}).mappings().all()

    licencias = db.execute(text("""
        SELECT producto, tipo, proveedor, fecha_vencimiento::text,
               activaciones_max, activaciones_usadas,
               CASE WHEN fecha_vencimiento IS NULL THEN 'sin_fecha'
                    WHEN fecha_vencimiento < CURRENT_DATE THEN 'vencida'
                    WHEN fecha_vencimiento <= CURRENT_DATE + INTERVAL '90 days' THEN 'por_vencer'
                    ELSE 'vigente' END AS estado
        FROM licencia WHERE cliente_id=:cid
    """), {"cid": cliente_id}).mappings().all()

    return {
        "cliente_nombre": nombre,
        "equipos": [dict(e) for e in equipos],
        "endpoints": [dict(e) for e in endpoints],
        "licencias": [dict(l) for l in licencias],
        "resumen": {
            "Total equipos": len(equipos),
            "Total endpoints": len(endpoints),
            "Total licencias": len(licencias),
        }
    }
