"""Construye contexto para el informe de trazabilidad por endpoint."""
from sqlalchemy import text


def construir(db, cliente_id, endpoint_id=None, **kwargs) -> dict:
    cli = db.execute(text("SELECT name FROM clients WHERE id=:id"), {"id": cliente_id}).mappings().first()
    nombre_cli = cli["name"] if cli else "—"

    if endpoint_id:
        ep_rows = db.execute(text("""
            SELECT ep.id::text, ep.nombre, ep.tipo, ep.ip, ep.mac, ep.habitacion,
                   ep.hostname, ep.extension_pbx, ep.notas,
                   s.nombre AS sitio_nombre
            FROM endpoint ep
            LEFT JOIN sitio s ON s.id = ep.sitio_id
            WHERE ep.id=:id AND ep.cliente_id=:cid
        """), {"id": endpoint_id, "cid": cliente_id}).mappings().all()
    else:
        ep_rows = db.execute(text("""
            SELECT ep.id::text, ep.nombre, ep.tipo, ep.ip, ep.mac, ep.habitacion,
                   ep.hostname, ep.extension_pbx, ep.notas,
                   s.nombre AS sitio_nombre
            FROM endpoint ep
            LEFT JOIN sitio s ON s.id = ep.sitio_id
            WHERE ep.cliente_id=:cid ORDER BY ep.nombre
        """), {"cid": cliente_id}).mappings().all()

    endpoints = [dict(e) for e in ep_rows]

    for ep in endpoints:
        traza = db.execute(text(
            "SELECT hops, resumen, hops_count, calculado_en::text FROM traza WHERE endpoint_id=:id"
        ), {"id": ep["id"]}).mappings().first()

        if traza:
            import json
            hops_raw = traza["hops"]
            hops = json.loads(hops_raw) if isinstance(hops_raw, str) else (hops_raw or [])
            ep["hops"] = hops
            ep["hops_count"] = traza["hops_count"] or len(hops)
            ep["resumen"] = traza["resumen"] or "—"
            ep["calculado_en"] = traza["calculado_en"] or "—"
            ep["estado_global"] = "documentada"
        else:
            ep["hops"] = []
            ep["hops_count"] = 0
            ep["resumen"] = "Sin traza documentada"
            ep["calculado_en"] = "—"
            ep["estado_global"] = "sin_traza"

    return {
        "cliente_nombre": nombre_cli,
        "endpoints": endpoints,
        "total": len(endpoints),
        "con_traza": sum(1 for e in endpoints if e["estado_global"] == "documentada"),
        "sin_traza": sum(1 for e in endpoints if e["estado_global"] == "sin_traza"),
    }
