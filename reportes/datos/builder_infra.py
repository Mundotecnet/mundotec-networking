"""Construye contexto para el informe de infraestructura."""
from sqlalchemy import text


def construir(db, cliente_id, sitios="all", incluir_credenciales=False) -> dict:
    # Cliente
    cli = db.execute(text("SELECT id, name, email, phone, address FROM clients WHERE id=:id"),
                     {"id": cliente_id}).mappings().first()
    if not cli:
        raise ValueError(f"Cliente {cliente_id} no encontrado")
    ctx = {"cliente_id": cliente_id, "cliente_nombre": cli["name"],
            "cliente_email": cli["email"] or "—",
            "cliente_telefono": cli["phone"] or "—",
            "cliente_direccion": cli["address"] or "—"}

    # Sitios
    q_sitios = "SELECT id::text, nombre, direccion FROM sitio WHERE cliente_id=:cid"
    params = {"cid": cliente_id}
    rows = db.execute(text(q_sitios), params).mappings().all()

    sitios_data = []
    for s in rows:
        sid = s["id"]
        # Edificios → cuartos → gabinetes
        edifs = db.execute(text(
            "SELECT id::text, codigo, nombre FROM edificio WHERE sitio_id=:sid ORDER BY codigo"
        ), {"sid": sid}).mappings().all()

        edif_list = []
        for e in edifs:
            cuartos = db.execute(text(
                "SELECT id::text, codigo, nombre, piso FROM cuarto WHERE edificio_id=:eid ORDER BY codigo"
            ), {"eid": e["id"]}).mappings().all()
            cuarto_list = []
            for c in cuartos:
                gabs = db.execute(text(
                    "SELECT codigo, nombre, unidades_rack FROM gabinete WHERE cuarto_id=:cid ORDER BY codigo"
                ), {"cid": c["id"]}).mappings().all()
                cuarto_list.append({**dict(c), "gabinetes": [dict(g) for g in gabs]})
            edif_list.append({**dict(e), "cuartos": cuarto_list})

        # Equipos del sitio
        equipos = db.execute(text("""
            SELECT eq.nombre, eq.tipo, eq.marca, eq.modelo, eq.ip_gestion, eq.codigo_rack,
                   cu.nombre AS cuarto_nombre
            FROM equipo eq LEFT JOIN cuarto cu ON cu.id = eq.cuarto_id
            WHERE eq.sitio_id=:sid ORDER BY eq.nombre
        """), {"sid": sid}).mappings().all()

        # VLANs del sitio
        vlans = db.execute(text(
            "SELECT vlan_id, nombre, color_hex FROM vlan WHERE sitio_id=:sid ORDER BY vlan_id"
        ), {"sid": sid}).mappings().all()

        # Subredes del sitio
        subredes = db.execute(text("""
            SELECT sub.cidr::text AS cidr, sub.gateway::text AS gateway,
                   sub.tipo, sub.descripcion, v.nombre AS vlan_nombre
            FROM subred sub LEFT JOIN vlan v ON v.id=sub.vlan_id
            WHERE sub.sitio_id=:sid ORDER BY sub.cidr
        """), {"sid": sid}).mappings().all()

        # WAN
        wan = db.execute(text(
            "SELECT isp, producto, ip_publica::text AS ip_publica, ancho_banda_mbps FROM wan WHERE sitio_id=:sid"
        ), {"sid": sid}).mappings().all()

        sitios_data.append({
            "id": sid, "nombre": s["nombre"], "direccion": s["direccion"] or "—",
            "edificios": edif_list,
            "equipos": [dict(e) for e in equipos],
            "vlans": [dict(v) for v in vlans],
            "subredes": [dict(s) for s in subredes],
            "wan": [dict(w) for w in wan],
        })

    ctx["sitios"] = sitios_data
    ctx["total_sitios"] = len(sitios_data)
    ctx["total_equipos"] = sum(len(s["equipos"]) for s in sitios_data)

    # Licencias (sin credenciales)
    licencias = db.execute(text("""
        SELECT producto, tipo, proveedor, fecha_vencimiento::text,
               activaciones_max, activaciones_usadas,
               CASE WHEN fecha_vencimiento IS NULL THEN 'sin_fecha'
                    WHEN fecha_vencimiento < CURRENT_DATE THEN 'vencida'
                    WHEN fecha_vencimiento <= CURRENT_DATE + INTERVAL '90 days' THEN 'por_vencer'
                    ELSE 'vigente' END AS estado
        FROM licencia WHERE cliente_id=:cid ORDER BY fecha_vencimiento NULLS LAST
    """), {"cid": cliente_id}).mappings().all()
    ctx["licencias"] = [dict(l) for l in licencias]

    if incluir_credenciales:
        creds = db.execute(text("""
            SELECT servicio, usuario, url FROM credencial WHERE cliente_id=:cid ORDER BY servicio
        """), {"cid": cliente_id}).mappings().all()
        ctx["credenciales"] = [dict(c) for c in creds]
    else:
        ctx["credenciales"] = []

    return ctx
