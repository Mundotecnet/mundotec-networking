"""Construye contexto para el informe de mantenimiento preventivo."""
from sqlalchemy import text


def construir(db, cliente_id, **kwargs) -> dict:
    cli = db.execute(text("SELECT name FROM clients WHERE id=:id"), {"id": cliente_id}).mappings().first()
    nombre = cli["name"] if cli else "—"

    licencias_por_vencer = db.execute(text("""
        SELECT producto, tipo, proveedor, fecha_vencimiento::text,
               (fecha_vencimiento - CURRENT_DATE) AS dias_restantes
        FROM licencia WHERE cliente_id=:cid
          AND fecha_vencimiento IS NOT NULL
          AND fecha_vencimiento <= CURRENT_DATE + INTERVAL '90 days'
        ORDER BY fecha_vencimiento
    """), {"cid": cliente_id}).mappings().all()

    equipos = db.execute(text("""
        SELECT eq.nombre, eq.tipo, eq.marca, eq.modelo, eq.ip_gestion,
               '' AS estado,
               s.nombre AS sitio_nombre
        FROM equipo eq LEFT JOIN sitio s ON s.id=eq.sitio_id
        WHERE eq.cliente_id=:cid ORDER BY eq.nombre
    """), {"cid": cliente_id}).mappings().all()

    recomendaciones = []
    for lic in licencias_por_vencer:
        dias = lic["dias_restantes"]
        sev = "alta" if dias and dias < 30 else "media"
        recomendaciones.append({
            "severidad": sev,
            "descripcion": f"Renovar licencia '{lic['producto']}' — vence en {dias} días",
            "costo_estimado": "—",
        })

    return {
        "cliente_nombre": nombre,
        "licencias_por_vencer": [dict(l) for l in licencias_por_vencer],
        "equipos": [dict(e) for e in equipos],
        "recomendaciones": recomendaciones,
        "total_equipos": len(equipos),
    }
