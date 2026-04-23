"""Construye contexto para el informe de infraestructura — esquema actual."""
from sqlalchemy import text


def construir(db, cliente_id, sitios="all", incluir_credenciales=False) -> dict:
    # ── Cliente ────────────────────────────────────────────────────────────────
    cli = db.execute(text(
        "SELECT id, name, email, phone, address FROM clients WHERE id=:id"
    ), {"id": cliente_id}).mappings().first()
    if not cli:
        raise ValueError(f"Cliente {cliente_id} no encontrado")

    ctx = {
        "cliente_id": cliente_id,
        "cliente_nombre": cli["name"],
        "cliente_email": cli["email"] or "—",
        "cliente_telefono": cli["phone"] or "—",
        "cliente_direccion": cli["address"] or "—",
    }

    # ── Edificios del cliente ──────────────────────────────────────────────────
    buildings = db.execute(text("""
        SELECT id, name, letter, address, notes
        FROM buildings WHERE client_id=:cid ORDER BY name
    """), {"cid": cliente_id}).mappings().all()

    sitios_data = []
    total_equipos = 0

    for bld in buildings:
        bid = bld["id"]

        # Cuartos del edificio
        rooms = db.execute(text("""
            SELECT id, name, letter, location, notes
            FROM rooms WHERE building_id=:bid ORDER BY name
        """), {"bid": bid}).mappings().all()

        cuarto_list = []
        equipos_sitio = []
        vlans_sitio = []

        for rm in rooms:
            rid = rm["id"]

            # Gabinetes del cuarto
            gabs = db.execute(text("""
                SELECT name, rack_units FROM cabinets WHERE room_id=:rid ORDER BY name
            """), {"rid": rid}).mappings().all()

            cuarto_list.append({
                "codigo": rm["letter"] or rm["name"][:3].upper(),
                "nombre": rm["name"],
                "piso": rm["location"] or "—",
                "gabinetes": [{"nombre": g["name"]} for g in gabs],
            })

            # Equipos del cuarto (activos de red primero)
            devs = db.execute(text("""
                SELECT name, device_type, brand, model, ip, mac, hostname,
                       serial, category, port_count
                FROM devices WHERE room_id=:rid ORDER BY category, name
            """), {"rid": rid}).mappings().all()

            for d in devs:
                equipos_sitio.append({
                    "nombre": d["name"],
                    "tipo": d["device_type"],
                    "marca": d["brand"] or "—",
                    "modelo": d["model"] or "—",
                    "ip_gestion": d["ip"] or "—",
                    "cuarto_nombre": rm["name"],
                    "estado": "activo",
                    "mac": d["mac"] or "—",
                    "hostname": d["hostname"] or "—",
                    "serial": d["serial"] or "—",
                    "categoria": d["category"],
                })

            # VLANs del cuarto
            vlans = db.execute(text("""
                SELECT vlan_id, name, subnet, gateway, dhcp, notes
                FROM vlans WHERE room_id=:rid ORDER BY vlan_id
            """), {"rid": rid}).mappings().all()

            for v in vlans:
                vlans_sitio.append({
                    "vlan_id": v["vlan_id"],
                    "nombre": v["name"] or f"VLAN {v['vlan_id']}",
                    "cidr": v["subnet"] or "—",
                    "gateway": v["gateway"] or "—",
                    "dhcp": v["dhcp"],
                })

        # Subredes construidas desde VLANs con subnet definida
        subredes = [
            {
                "cidr": v["cidr"],
                "gateway": v["gateway"],
                "vlan_nombre": f"VLAN {v['vlan_id']} {v['nombre']}",
                "tipo": "LAN",
                "descripcion": v["nombre"],
            }
            for v in vlans_sitio if v["cidr"] != "—"
        ]

        # WAN del sitio (tabla legacy si existe y tiene data)
        wan = []
        try:
            wan_rows = db.execute(text("""
                SELECT isp, producto, ip_publica::text AS ip_publica, ancho_banda_mbps
                FROM wan WHERE sitio_id IN (
                    SELECT id FROM sitio WHERE cliente_id=:cid
                )
            """), {"cid": cliente_id}).mappings().all()
            wan = [dict(w) for w in wan_rows]
        except Exception:
            pass

        # Patch panels del edificio (resumen)
        pp_count = db.execute(text("""
            SELECT COUNT(*) FROM patch_panels pp
            JOIN rooms r ON r.id = pp.room_id
            WHERE r.building_id=:bid
        """), {"bid": bid}).scalar() or 0

        total_equipos += len(equipos_sitio)

        sitios_data.append({
            "id": bid,
            "nombre": bld["name"],
            "direccion": bld["address"] or "—",
            "edificios": [{
                "codigo": bld["letter"] or bld["name"][:3].upper(),
                "nombre": bld["name"],
                "cuartos": cuarto_list,
            }],
            "equipos": equipos_sitio,
            "vlans": vlans_sitio,
            "subredes": subredes,
            "wan": wan,
            "pp_count": pp_count,
        })

    ctx["sitios"] = sitios_data
    ctx["total_sitios"] = len(sitios_data)
    ctx["total_equipos"] = total_equipos

    # ── Licencias ──────────────────────────────────────────────────────────────
    try:
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
    except Exception:
        ctx["licencias"] = []

    # ── Credenciales ───────────────────────────────────────────────────────────
    if incluir_credenciales:
        try:
            creds = db.execute(text("""
                SELECT servicio, usuario, url FROM credencial
                WHERE cliente_id=:cid ORDER BY servicio
            """), {"cid": cliente_id}).mappings().all()
            ctx["credenciales"] = [dict(c) for c in creds]
        except Exception:
            ctx["credenciales"] = []
    else:
        ctx["credenciales"] = []

    return ctx
