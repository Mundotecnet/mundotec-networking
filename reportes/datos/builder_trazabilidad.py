"""Construye contexto para el informe de trazabilidad por endpoint."""
from sqlalchemy import text


def construir(db, cliente_id, endpoint_id=None, **kwargs) -> dict:
    cli = db.execute(text("SELECT name FROM clients WHERE id=:id"), {"id": cliente_id}).mappings().first()
    nombre_cli = cli["name"] if cli else "—"

    if endpoint_id:
        ep = db.execute(text("""
            SELECT ep.id::text, ep.nombre, ep.tipo, ep.ip, ep.mac, ep.habitacion,
                   s.nombre AS sitio_nombre, c.name AS cliente_nombre
            FROM endpoint ep LEFT JOIN sitio s ON s.id=ep.sitio_id
            JOIN clients c ON c.id=ep.cliente_id
            WHERE ep.id=:id
        """), {"id": endpoint_id}).mappings().first()
        endpoints = [dict(ep)] if ep else []
    else:
        endpoints = db.execute(text("""
            SELECT ep.id::text, ep.nombre, ep.tipo, ep.ip, ep.mac, ep.habitacion,
                   s.nombre AS sitio_nombre
            FROM endpoint ep LEFT JOIN sitio s ON s.id=ep.sitio_id
            WHERE ep.cliente_id=:cid ORDER BY ep.nombre LIMIT 20
        """), {"cid": cliente_id}).mappings().all()
        endpoints = [dict(e) for e in endpoints]

    # Agregar hops de traza si existen
    for ep in endpoints:
        traza = db.execute(text(
            "SELECT hops, estado_global, resumen FROM traza WHERE endpoint_id=:id"
        ), {"id": ep["id"]}).mappings().first()
        if traza:
            import json
            hops_raw = traza["hops"]
            ep["hops"] = json.loads(hops_raw) if isinstance(hops_raw, str) else hops_raw or []
            ep["estado_global"] = traza["estado_global"]
            ep["resumen"] = traza["resumen"]
        else:
            ep["hops"] = []
            ep["estado_global"] = "sin_traza"
            ep["resumen"] = "Sin traza documentada"

    return {"cliente_nombre": nombre_cli, "endpoints": endpoints, "total": len(endpoints)}
