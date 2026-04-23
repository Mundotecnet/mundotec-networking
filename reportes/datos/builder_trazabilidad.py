"""Construye contexto para el informe de trazabilidad — mapa patch panel → switch."""
from sqlalchemy import text


def construir(db, cliente_id, **kwargs) -> dict:
    cli = db.execute(text("SELECT name FROM clients WHERE id=:id"),
                     {"id": cliente_id}).mappings().first()
    if not cli:
        raise ValueError(f"Cliente {cliente_id} no encontrado")

    # Edificios → cuartos → paneles → puertos
    buildings = db.execute(text("""
        SELECT id, name FROM buildings WHERE client_id=:cid ORDER BY name
    """), {"cid": cliente_id}).mappings().all()

    edificios = []
    totales = {"total": 0, "con_switch": 0, "sin_switch": 0,
               "completos": 0, "parciales": 0, "sin_revisar": 0}

    for bld in buildings:
        rooms = db.execute(text("""
            SELECT id, name FROM rooms WHERE building_id=:bid ORDER BY name
        """), {"bid": bld["id"]}).mappings().all()

        cuartos = []
        for rm in rooms:
            panels = db.execute(text("""
                SELECT id, name FROM patch_panels WHERE room_id=:rid ORDER BY name
            """), {"rid": rm["id"]}).mappings().all()

            paneles = []
            for pan in panels:
                puertos = db.execute(text("""
                    SELECT
                        pp.number, pp.label, pp.node_type,
                        pp.node_description, pp.node_mac, pp.node_ip,
                        pp.status, pp.completeness_status, pp.notes,
                        dp.port_number  AS sw_puerto,
                        dp.port_mode    AS sw_modo,
                        dp.vlan_id      AS sw_vlan_id,
                        d.name          AS sw_nombre,
                        d.ip            AS sw_ip,
                        d.device_type   AS sw_tipo,
                        v.vlan_id       AS vlan_num,
                        v.name          AS vlan_nombre
                    FROM patch_ports pp
                    LEFT JOIN device_ports dp ON dp.id = pp.switch_port_id
                    LEFT JOIN devices d       ON d.id  = dp.device_id
                    LEFT JOIN vlans v         ON v.id  = dp.vlan_id
                    WHERE pp.patch_panel_id = :pid
                    ORDER BY pp.number
                """), {"pid": pan["id"]}).mappings().all()

                rows = []
                for p in puertos:
                    totales["total"] += 1
                    cs = p["completeness_status"] or "sin_revisar"
                    if cs == "completo":
                        totales["completos"] += 1
                    elif cs == "parcial":
                        totales["parciales"] += 1
                    else:
                        totales["sin_revisar"] += 1

                    if p["sw_nombre"]:
                        totales["con_switch"] += 1
                    else:
                        totales["sin_switch"] += 1

                    sw_puerto_fmt = ""
                    if p["sw_nombre"]:
                        num = str(int(p["sw_puerto"])).zfill(2) if p["sw_puerto"] else "?"
                        sw_puerto_fmt = f"{p['sw_nombre']} p:{num}"
                        if p["sw_modo"]:
                            sw_puerto_fmt += f" ({p['sw_modo']})"

                    vlan_str = ""
                    if p["vlan_num"]:
                        vlan_str = f"VLAN {p['vlan_num']}"
                        if p["vlan_nombre"]:
                            vlan_str += f" — {p['vlan_nombre']}"

                    rows.append({
                        "numero": p["number"],
                        "etiqueta": p["label"] or "—",
                        "descripcion": p["node_description"] or "—",
                        "ip": p["node_ip"] or "—",
                        "mac": p["node_mac"] or "—",
                        "tipo": p["node_type"] or "libre",
                        "estado": p["completeness_status"] or "sin_revisar",
                        "sw_destino": sw_puerto_fmt or "—",
                        "vlan": vlan_str or "—",
                        "notas": p["notes"] or "",
                    })

                paneles.append({
                    "nombre": pan["name"],
                    "puertos": rows,
                    "total": len(rows),
                    "con_switch": sum(1 for r in rows if r["sw_destino"] != "—"),
                })

            if paneles:
                cuartos.append({
                    "nombre": rm["name"],
                    "paneles": paneles,
                })

        if cuartos:
            edificios.append({
                "nombre": bld["name"],
                "cuartos": cuartos,
            })

    return {
        "cliente_nombre": cli["name"],
        "edificios": edificios,
        **totales,
    }
