from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import models


def evaluate_port(port: "models.PatchPort", room_has_switch: bool = False) -> str:
    """Compute the completeness status of a single PatchPort."""
    if port.node_type == "libre":
        return "libre"
    if port.node_type == "prevista":
        return "prevista"
    if port.node_type in ("device", "descripcion"):
        has_mac = bool(port.node_mac)
        has_ip = bool(port.node_ip)
        has_vlan = port.vlan_id is not None
        has_switch_link = port.switch_port_id is not None
        if has_mac and has_ip and has_vlan and (not room_has_switch or has_switch_link):
            return "completo"
        return "parcial"
    return "sin_revisar"


def pp_score(ports: list, room_has_switch: bool = False) -> dict:
    statuses = [evaluate_port(p, room_has_switch) for p in ports]
    completos = statuses.count("completo")
    parciales = statuses.count("parcial")
    sin_revisar = statuses.count("sin_revisar")
    libres = statuses.count("libre")
    previstas = statuses.count("prevista")
    evaluable = 24 - libres - previstas
    score = round(completos / evaluable * 100, 1) if evaluable > 0 else 100.0
    return {
        "completos": completos, "parciales": parciales,
        "sin_revisar": sin_revisar, "libres": libres,
        "previstas": previstas, "evaluable": evaluable,
        "score": score,
    }


def client_analytics(client: "models.Client") -> dict:
    """
    Returns full analytics for a client, including per-room breakdown
    and issue lists at error/warning/info levels.
    """
    errors: list[dict] = []
    warnings: list[dict] = []
    info: list[dict] = []

    total_completos = total_evaluable = 0
    by_room: list[dict] = []

    for room in client.rooms:
        room_has_switch = bool(room.switch_ip or room.switch_mac or room.switch_model)
        room_issues: list[dict] = []

        # Collect IPs and labels in this room for duplicate detection
        ips_seen: dict[str, list] = {}
        labels_seen: dict[str, list] = {}

        for panel in room.patch_panels:
            for port in panel.ports:
                cs = evaluate_port(port, room_has_switch)
                port.completeness_status = cs

                if port.label:
                    labels_seen.setdefault(port.label, []).append(port.id)
                if port.node_ip:
                    ips_seen.setdefault(port.node_ip, []).append(port.id)

                if cs == "sin_revisar":
                    info.append({
                        "level": "info", "code": "puerto_sin_revisar",
                        "room_id": room.id, "room_name": room.name,
                        "label": port.label or f"PP{port.patch_panel_id}:{port.number}",
                    })
                elif cs == "parcial":
                    fields = []
                    if not port.node_mac:
                        fields.append("MAC")
                    if not port.node_ip:
                        fields.append("IP")
                    if port.vlan_id is None:
                        fields.append("VLAN")
                    if room_has_switch and not port.switch_port_id:
                        fields.append("Puerto switch")
                    warnings.append({
                        "level": "warning", "code": "puerto_parcial",
                        "room_id": room.id, "room_name": room.name,
                        "label": port.label or f"PP{port.patch_panel_id}:{port.number}",
                        "fields": fields,
                    })

        # IP duplicates within room
        for ip, port_ids in ips_seen.items():
            if len(port_ids) > 1:
                errors.append({
                    "level": "error", "code": "ip_duplicada",
                    "room_id": room.id, "room_name": room.name,
                    "detail": f"IP {ip} en {len(port_ids)} puertos",
                })

        # Label duplicates within room
        for label, port_ids in labels_seen.items():
            if len(port_ids) > 1:
                errors.append({
                    "level": "error", "code": "etiqueta_duplicada",
                    "room_id": room.id, "room_name": room.name,
                    "detail": f"Etiqueta {label} en {len(port_ids)} puertos",
                })

        # Device warnings
        ADMIN_TYPES = {"switch", "router", "firewall", "ap", "servidor"}
        for dev in room.devices:
            if dev.device_type in ADMIN_TYPES:
                if not dev.username_encrypted or not dev.password_encrypted:
                    warnings.append({
                        "level": "warning", "code": "equipo_sin_credenciales",
                        "room_id": room.id, "room_name": room.name,
                        "label": dev.name,
                    })
                if not dev.mac:
                    warnings.append({
                        "level": "warning", "code": "equipo_sin_mac",
                        "room_id": room.id, "room_name": room.name,
                        "label": dev.name,
                    })
                if not dev.ip:
                    warnings.append({
                        "level": "warning", "code": "equipo_sin_ip",
                        "room_id": room.id, "room_name": room.name,
                        "label": dev.name,
                    })
                if dev.category == "activo_red" and dev.device_type in {"switch", "router", "firewall"}:
                    if not dev.backups:
                        info.append({
                            "level": "info", "code": "equipo_sin_backup",
                            "room_id": room.id, "room_name": room.name,
                            "label": dev.name,
                        })

        # Room score
        all_ports = [p for panel in room.patch_panels for p in panel.ports]
        sc = pp_score(all_ports, room_has_switch)
        total_completos += sc["completos"]
        total_evaluable += sc["evaluable"]
        by_room.append({
            "room_id": room.id,
            "room_name": room.name,
            "score": sc["score"],
            "completos": sc["completos"],
            "parciales": sc["parciales"],
            "sin_revisar": sc["sin_revisar"],
            "libres": sc["libres"],
            "previstas": sc["previstas"],
            "evaluable": sc["evaluable"],
            "issues": [i for i in (errors + warnings + info) if i.get("room_id") == room.id],
        })

    global_score = round(total_completos / total_evaluable * 100, 1) if total_evaluable > 0 else 100.0

    return {
        "client_id": client.id,
        "client_name": client.name,
        "score": global_score,
        "total_evaluable": total_evaluable,
        "completos": total_completos,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "by_room": by_room,
    }
