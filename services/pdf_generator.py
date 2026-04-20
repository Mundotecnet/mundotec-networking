"""
Generador de reportes PDF para MundoTec Networking.
"""
from io import BytesIO
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.colors import HexColor

import models
from services.completeness import evaluate_port, pp_score
from services.net_diagram import build_diagram_room, build_diagram_client
from services.crypto import decrypt
from reportlab.graphics import renderPDF
from reportlab.platypus import Flowable

PRIMARY   = HexColor("#1a3a5c")
ACCENT    = HexColor("#f39c12")
RED_BG    = HexColor("#7b1c1c")
WARN_BG   = HexColor("#fff3cd")
ERR_BG    = HexColor("#f8d7da")
GRAY_ROW  = HexColor("#f5f5f5")
GREEN_TXT = HexColor("#155724")
ORANGE    = HexColor("#856404")
STATUS_ICONS = {
    "completo":    "✓",
    "parcial":     "!",
    "libre":       "—",
    "prevista":    "~",
    "sin_revisar": "?",
}
STATUS_COLORS = {
    "completo":    HexColor("#d4edda"),
    "parcial":     WARN_BG,
    "libre":       HexColor("#e2e3e5"),
    "prevista":    HexColor("#e8d5ff"),
    "sin_revisar": ERR_BG,
}


class _DiagramFlowable(Flowable):
    def __init__(self, drawing, width):
        Flowable.__init__(self)
        self._drawing = drawing
        self.width = width
        self.height = drawing.height

    def draw(self):
        renderPDF.draw(self._drawing, self.canv, 0, 0)


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Header
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, h - 0.5 * inch, w, 0.5 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0.5 * inch, h - 0.33 * inch, "MUNDOTEC | Gestión de Redes")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 0.5 * inch, h - 0.33 * inch, doc._client_name)
    # Footer
    canvas.setFillColor(HexColor("#555555"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(0.5 * inch, 0.25 * inch,
                      f"Generado: {date.today().strftime('%d/%m/%Y')} | Documento confidencial")
    canvas.drawRightString(w - 0.5 * inch, 0.25 * inch, f"Pág. {doc.page}")
    canvas.restoreState()


def _ts(data, col_widths, header_bg=PRIMARY):
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRAY_ROW]),
        ("GRID",       (0, 0), (-1, -1), 0.3, HexColor("#cccccc")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(style))
    return t


def generate_client_report(
    db,
    client_id: int,
    include_recent_changes: bool = False,
) -> bytes:
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise ValueError("Cliente no encontrado")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.65 * inch, bottomMargin=0.45 * inch,
    )
    doc._client_name = client.name

    styles = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, textColor=PRIMARY, spaceAfter=6)
    H2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12, textColor=PRIMARY, spaceBefore=12, spaceAfter=4)
    H3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=9, spaceBefore=6, spaceAfter=3)
    NORMAL = styles["Normal"]
    NORMAL.fontSize = 8
    CONF = ParagraphStyle("CONF", fontName="Helvetica-Bold", fontSize=9,
                          textColor=colors.white, backColor=RED_BG)

    story = []

    # ── Cover Page ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * inch))
    story.append(Paragraph("REPORTE DE INFRAESTRUCTURA DE RED", H1))
    story.append(Paragraph(client.name, ParagraphStyle("CN", fontName="Helvetica-Bold",
                                                        fontSize=20, textColor=ACCENT, spaceAfter=8)))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    story.append(Spacer(1, 0.3 * inch))

    # Client info table
    from services.completeness import client_analytics
    analytics = client_analytics(client)
    total_rooms = len(client.rooms)
    total_devices = sum(len(r.devices) for r in client.rooms)
    total_ports = sum(len(pp.ports) for r in client.rooms for pp in r.patch_panels)

    info_data = [
        ["Nombre", client.name or ""],
        ["Teléfono", client.phone or ""],
        ["Email", client.email or ""],
        ["Dirección", client.address or ""],
        ["Contacto", client.contact or ""],
        ["Fecha de reporte", date.today().strftime("%d/%m/%Y")],
    ]
    t_info = Table(info_data, colWidths=[1.5 * inch, 5 * inch])
    t_info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GRAY_ROW, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 0.2 * inch))

    summary_data = [
        ["Cuartos", "Puertos", "Equipos", "Completitud"],
        [str(total_rooms), str(total_ports), str(total_devices),
         f"{analytics['score']:.1f}%"],
    ]
    story.append(_ts(summary_data, [1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch]))
    story.append(Spacer(1, 0.2 * inch))

    # Global network diagram
    try:
        diagram = build_diagram_client(client, width=6 * inch)
        story.append(_DiagramFlowable(diagram, 6 * inch))
    except Exception:
        pass

    story.append(PageBreak())

    # ── Per Room Pages ───────────────────────────────────────────────────────
    for room in client.rooms:
        room_has_switch = bool(room.switch_ip or room.switch_mac or room.switch_model)
        story.append(Paragraph(f"Cuarto: {room.name}", H1))
        if room.location:
            story.append(Paragraph(f"Ubicación: {room.location}", NORMAL))

        # Switch / AP
        if room.switch_model or room.switch_ip or room.ap_model:
            story.append(Paragraph("Información de equipos principales", H2))
            sw_data = [["Equipo", "Modelo", "MAC", "IP"]]
            if room.switch_model or room.switch_ip:
                sw_data.append(["Switch", room.switch_model or "", room.switch_mac or "", room.switch_ip or ""])
            if room.ap_model:
                sw_data.append(["AP", room.ap_model or "", room.ap_mac or "", room.ap_ip or ""])
            story.append(_ts(sw_data, [1 * inch, 2 * inch, 2 * inch, 1.5 * inch]))
            story.append(Spacer(1, 0.1 * inch))

        # VLANs
        if room.vlans:
            story.append(Paragraph("VLANs", H2))
            vlan_data = [["ID", "Nombre", "Subred", "Gateway", "DHCP"]]
            for v in room.vlans:
                vlan_data.append([str(v.vlan_id), v.name, v.subnet or "", v.gateway or "",
                                   "Sí" if v.dhcp else "No"])
            story.append(_ts(vlan_data, [0.6*inch, 2*inch, 1.8*inch, 1.8*inch, 0.8*inch]))
            story.append(Spacer(1, 0.1 * inch))

        # Active network devices
        red_devs = [d for d in room.devices if d.category == "activo_red"]
        final_devs = [d for d in room.devices if d.category == "activo_final"]

        if red_devs:
            story.append(Paragraph("Equipos activos de red", H2))
            dev_data = [["Nombre", "Tipo", "Marca/Modelo", "IP", "MAC", "Admin"]]
            for d in red_devs:
                dev_data.append([
                    d.name, d.device_type,
                    f"{d.brand} {d.model}".strip(),
                    d.ip or "", d.mac or "", d.admin_port or "",
                ])
            story.append(_ts(dev_data, [1.5*inch, 1*inch, 1.8*inch, 1.2*inch, 1.5*inch, 0.8*inch]))
            story.append(Spacer(1, 0.1 * inch))

        if final_devs:
            story.append(Paragraph("Equipos activos finales", H2))
            fin_data = [["Nombre", "Tipo", "Marca/Modelo", "IP", "MAC"]]
            for d in final_devs:
                fin_data.append([d.name, d.device_type, f"{d.brand} {d.model}".strip(),
                                  d.ip or "", d.mac or ""])
            story.append(_ts(fin_data, [2*inch, 1*inch, 2*inch, 1.2*inch, 1.5*inch]))
            story.append(Spacer(1, 0.1 * inch))

        # Patch panels
        if room.patch_panels:
            story.append(Paragraph("Equipos pasivos — Patch Panels", H2))
            for pp in room.patch_panels:
                ports = sorted(pp.ports, key=lambda p: p.number)
                sc = pp_score(ports, room_has_switch)
                story.append(Paragraph(
                    f"{pp.name} — {pp.brand or ''} {pp.model or ''} — "
                    f"Piso {pp.floor} · Formato {pp.format}",
                    H3
                ))
                story.append(Paragraph(
                    f"Completitud: {sc['completos']}/24  ✓:{sc['completos']} "
                    f"!:{sc['parciales']} ?:{sc['sin_revisar']} —:{sc['libres']} ~:{sc['previstas']}",
                    NORMAL
                ))

                port_data = [["#", "Etiqueta", "Nodo", "MAC", "IP", "VLAN", "SW:Pto", "Estado"]]
                for port in ports:
                    cs = evaluate_port(port, room_has_switch)
                    vlan_name = ""
                    if port.vlan_id:
                        v = next((vl for vl in room.vlans if vl.id == port.vlan_id), None)
                        if v:
                            vlan_name = str(v.vlan_id)
                    sw_port_label = ""
                    if port.switch_port_id and port.switch_port:
                        sw_port_label = port.switch_port.port_number

                    if port.node_type == "device" and port.device:
                        nodo = port.device.name
                    elif port.node_type == "descripcion":
                        nodo = (port.node_description or "")[:30]
                    elif port.node_type == "libre":
                        nodo = "LIBRE"
                    elif port.node_type == "prevista":
                        nodo = "PREVISTA"
                    else:
                        nodo = ""

                    port_data.append([
                        str(port.number),
                        port.label or "",
                        nodo,
                        port.node_mac or "",
                        port.node_ip or "",
                        vlan_name,
                        sw_port_label,
                        STATUS_ICONS.get(cs, "?"),
                    ])

                t_pp = Table(
                    port_data,
                    colWidths=[0.3*inch, 0.8*inch, 1.3*inch, 1.2*inch, 1*inch, 0.5*inch, 0.5*inch, 0.5*inch]
                )
                pp_style = [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#37474f")),
                    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",   (0, 0), (-1, -1), 6.5),
                    ("GRID",       (0, 0), (-1, -1), 0.3, HexColor("#cccccc")),
                    ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ]
                for row_idx, port in enumerate(ports, start=1):
                    cs = evaluate_port(port, room_has_switch)
                    bg = STATUS_COLORS.get(cs, colors.white)
                    if bg != colors.white:
                        pp_style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg))
                t_pp.setStyle(TableStyle(pp_style))
                story.append(KeepTogether([t_pp, Spacer(1, 0.1 * inch)]))

        # Credentials (red section)
        creds_devs = [d for d in room.devices if d.username_encrypted or d.password_encrypted]
        if creds_devs:
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph("⚠ DATOS DE ACCESO — INFORMACIÓN CONFIDENCIAL", CONF))
            cred_data = [["Equipo", "Usuario", "Contraseña"]]
            for d in creds_devs:
                try:
                    username = decrypt(d.username_encrypted) if d.username_encrypted else ""
                    password = decrypt(d.password_encrypted) if d.password_encrypted else ""
                except Exception:
                    username = "[error]"
                    password = "[error]"
                cred_data.append([d.name, username, password])
            t_cred = Table(cred_data, colWidths=[2*inch, 2*inch, 2.5*inch])
            t_cred.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), RED_BG),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 7.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#fff0f0"), colors.white]),
                ("GRID",       (0, 0), (-1, -1), 0.3, HexColor("#ffaaaa")),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t_cred)

        # Connections
        if room.connections:
            story.append(Paragraph("Interconexiones", H2))
            for conn in room.connections:
                story.append(Paragraph(f"• {conn.description or ''} — {conn.notes or ''}", NORMAL))

        # Room diagram
        try:
            rm_diag = build_diagram_room(room, width=6 * inch)
            story.append(Spacer(1, 0.1 * inch))
            story.append(_DiagramFlowable(rm_diag, 6 * inch))
        except Exception:
            pass

        story.append(PageBreak())

    # ── Recent changes ───────────────────────────────────────────────────────
    if include_recent_changes:
        story.append(Paragraph("Registro de cambios recientes (últimos 30 días)", H1))
        from datetime import datetime, timedelta, timezone
        since = datetime.now(timezone.utc) - timedelta(days=30)
        logs = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.client_id == client_id,
                models.AuditLog.timestamp >= since,
            )
            .order_by(models.AuditLog.timestamp.desc())
            .limit(50)
            .all()
        )
        chg_data = [["Fecha", "Usuario", "Acción", "Elemento"]]
        for entry in logs:
            chg_data.append([
                entry.timestamp.strftime("%d/%m/%Y %H:%M") if entry.timestamp else "",
                entry.user_name or "",
                entry.action,
                f"{entry.entity_type} #{entry.entity_id}" if entry.entity_id else entry.entity_type,
            ])
        story.append(_ts(chg_data, [1.4*inch, 1.4*inch, 1.6*inch, 2.3*inch]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
