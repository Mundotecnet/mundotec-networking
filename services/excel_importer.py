"""
Importador Excel para MundoTec Networking.
Cada hoja = un cuarto. Columnas: PUERTO | DETALLE | MAC | PUERTO SWITCH
"""
import re
from io import BytesIO
from typing import Any
import openpyxl
from sqlalchemy.orm import Session
import models

# ── Type detection ─────────────────────────────────────────────────────────────

_PATTERNS = {
    "camara":    re.compile(r"(cam|camara|camera)", re.I),
    "ap":        re.compile(r"(^ap[- /]|access.pt)", re.I),
    "estacion":  re.compile(r"(estacion|pc\b|maquina|maq|workstation)", re.I),
    "prevista":  re.compile(r"prevista", re.I),
    "libre":     re.compile(r"^libre$", re.I),
    "pbx":       re.compile(r"(pbx|central)", re.I),
    "impresora": re.compile(r"(impresora|printer)", re.I),
    "nvr":       re.compile(r"\bnvr\b", re.I),
    "dvr":       re.compile(r"\bdvr\b", re.I),
}


def _detect_type(detail: str) -> str:
    detail = (detail or "").strip()
    for key, pat in _PATTERNS.items():
        if pat.search(detail):
            return key
    return "otro"


def _clean_mac(raw: str) -> tuple[str, str | None]:
    """Returns (mac, ip_if_found)."""
    raw = (raw or "").strip()
    ip = None
    if "IP:" in raw.upper():
        match = re.search(r"IP:\s*([\d.]+)", raw, re.I)
        if match:
            ip = match.group(1)
        raw = re.sub(r"IP:.*", "", raw, flags=re.I).strip(" ;,")
    return raw, ip


def _clean_sw_port(raw: str) -> str:
    raw = (raw or "").strip()
    if re.match(r"^\d+\.0$", raw):
        return raw.split(".")[0]
    return raw


def _detect_format(label: str) -> str:
    if re.match(r"^[0-9][A-Z]-[A-Z]-[A-Z][0-9]{2}$", label):
        return "full"
    return "simple"


def _generate_label(pp: models.PatchPanel, port_number: int) -> str:
    num_str = f"{port_number:02d}"
    if pp.format == "full":
        return f"{pp.floor}{pp.room_letter}-{pp.building or 'A'}-{pp.panel_letter}{num_str}"
    return f"{pp.floor}{pp.room_letter}-{pp.panel_letter}{num_str}"


# ── Meta info detection in first 8 rows ───────────────────────────────────────

def _extract_room_meta(ws) -> dict:
    meta: dict[str, Any] = {}
    for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
        row_text = " ".join(str(c) for c in row if c)
        sw_m = re.search(r"switch[:\s]+([\w\s-]+)", row_text, re.I)
        if sw_m:
            meta["switch_model"] = sw_m.group(1).strip()[:100]
        ip_m = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", row_text)
        if ip_m and "switch_ip" not in meta:
            meta["switch_ip"] = ip_m.group(1)
        mac_m = re.search(r"([0-9A-Fa-f]{2}[:\-][0-9A-Fa-f]{2}[:\-][0-9A-Fa-f]{2}[:\-][0-9A-Fa-f]{2}[:\-][0-9A-Fa-f]{2}[:\-][0-9A-Fa-f]{2})", row_text)
        if mac_m and "switch_mac" not in meta:
            meta["switch_mac"] = mac_m.group(1)
        ap_m = re.search(r"ap[:\s]+([\w\s-]+)", row_text, re.I)
        if ap_m:
            meta["ap_model"] = ap_m.group(1).strip()[:100]
        loc_m = re.search(r"ubicaci[oó]n[:\s]+(.+)", row_text, re.I)
        if loc_m:
            meta["location"] = loc_m.group(1).strip()[:255]
    return meta


# ── Main importer ──────────────────────────────────────────────────────────────

def import_excel(
    db: Session,
    file_content: bytes,
    client_name: str,
    current_user: models.User | None = None,
) -> dict:
    wb = openpyxl.load_workbook(BytesIO(file_content), data_only=True)
    rooms_created = 0
    ports_imported = 0
    warnings: list[str] = []

    # Find or create client
    client = db.query(models.Client).filter(
        models.Client.name.ilike(client_name)
    ).first()
    if not client:
        client = models.Client(name=client_name)
        db.add(client)
        db.flush()

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        meta = _extract_room_meta(ws)

        room = db.query(models.Room).filter(
            models.Room.client_id == client.id,
            models.Room.name == sheet_name,
        ).first()
        if not room:
            room = models.Room(
                client_id=client.id,
                name=sheet_name,
                location=meta.get("location", ""),
                switch_model=meta.get("switch_model"),
                switch_mac=meta.get("switch_mac"),
                switch_ip=meta.get("switch_ip"),
                ap_model=meta.get("ap_model"),
            )
            db.add(room)
            db.flush()
            rooms_created += 1

        # Detect headers row (find row containing "PUERTO")
        header_row_idx = None
        for row in ws.iter_rows(min_row=1, max_row=15):
            for cell in row:
                if cell.value and "PUERTO" in str(cell.value).upper():
                    header_row_idx = cell.row
                    break
            if header_row_idx:
                break

        if not header_row_idx:
            warnings.append(f"Hoja '{sheet_name}': no se encontró fila de encabezados")
            continue

        headers = [str(c.value).strip().upper() if c.value else "" for c in ws[header_row_idx]]
        col_puerto = next((i for i, h in enumerate(headers) if "PUERTO" in h), None)
        col_detalle = next((i for i, h in enumerate(headers) if "DETALLE" in h), None)
        col_mac = next((i for i, h in enumerate(headers) if "MAC" in h), None)
        col_sw = next((i for i, h in enumerate(headers) if "SWITCH" in h or "SW" in h), None)

        if col_puerto is None:
            warnings.append(f"Hoja '{sheet_name}': columna PUERTO no encontrada")
            continue

        # Group ports into patches of 24
        port_data: list[dict] = []
        for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
            if all(c is None for c in row):
                continue
            entry: dict = {}
            if col_puerto is not None and col_puerto < len(row):
                entry["port_label"] = str(row[col_puerto] or "").strip()
            if col_detalle is not None and col_detalle < len(row):
                entry["detail"] = str(row[col_detalle] or "").strip()
            if col_mac is not None and col_mac < len(row):
                raw_mac = str(row[col_mac] or "").strip()
                mac, ip = _clean_mac(raw_mac)
                entry["mac"] = mac
                entry["ip_from_mac"] = ip
            else:
                entry["mac"] = ""
                entry["ip_from_mac"] = None
            if col_sw is not None and col_sw < len(row):
                entry["sw_port"] = _clean_sw_port(str(row[col_sw] or ""))
            if entry.get("port_label") or entry.get("detail"):
                port_data.append(entry)

        if not port_data:
            warnings.append(f"Hoja '{sheet_name}': sin datos de puertos")
            continue

        # Determine label format from first labeled port
        label_format = "simple"
        for e in port_data:
            lbl = e.get("port_label", "")
            if lbl and re.match(r"^[0-9][A-Z]-[A-Z]-[A-Z][0-9]{2}$", lbl):
                label_format = "full"
                break

        # Parse PP info from first label
        first_label = next((e["port_label"] for e in port_data if e.get("port_label")), "")
        floor, room_letter, building, panel_letter = 1, "A", None, "A"
        if label_format == "full" and re.match(r"^([0-9])([A-Z])-([A-Z])-([A-Z])", first_label):
            m = re.match(r"^([0-9])([A-Z])-([A-Z])-([A-Z])", first_label)
            floor, room_letter, building, panel_letter = int(m[1]), m[2], m[3], m[4]
        elif re.match(r"^([0-9])([A-Z])-([A-Z])", first_label):
            m = re.match(r"^([0-9])([A-Z])-([A-Z])", first_label)
            floor, room_letter, panel_letter = int(m[1]), m[2], m[3]

        # Create patch panel
        pp = models.PatchPanel(
            room_id=room.id,
            name=f"PP-{panel_letter}",
            floor=floor,
            building=building,
            room_letter=room_letter,
            panel_letter=panel_letter,
            format=label_format,
        )
        db.add(pp)
        db.flush()

        # Create 24 ports
        for i in range(1, 25):
            label = _generate_label(pp, i)
            idx = i - 1
            if idx < len(port_data):
                e = port_data[idx]
                detail = e.get("detail", "")
                detected = _detect_type(detail)
                if detected == "libre":
                    node_type, status = "libre", "libre"
                elif detected == "prevista":
                    node_type, status = "prevista", "prevista"
                else:
                    node_type, status = "descripcion", "sin_revisar"

                port = models.PatchPort(
                    patch_panel_id=pp.id,
                    number=i,
                    label=e.get("port_label") or label,
                    node_type=node_type if detected not in ("libre", "prevista") else detected,
                    node_description=detail if detected not in ("libre", "prevista") else None,
                    node_mac=e.get("mac") or None,
                    node_ip=e.get("ip_from_mac") or None,
                    status=status,
                    completeness_status=status,
                )
            else:
                port = models.PatchPort(
                    patch_panel_id=pp.id,
                    number=i,
                    label=label,
                    status="sin_revisar",
                    completeness_status="sin_revisar",
                )
            db.add(port)
            ports_imported += 1

    db.commit()
    return {
        "client_id": client.id,
        "rooms_created": rooms_created,
        "ports_imported": ports_imported,
        "warnings": warnings,
    }
