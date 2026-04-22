"""Renderizador XLSX para el informe de inventario."""
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


NAVY = "0F1E44"
TEAL = "1C7293"
AMBER = "F2A65A"
LIGHT = "F5F7FA"


def _header_style(ws, row, cols, color=NAVY):
    fill = PatternFill("solid", fgColor=color)
    font = Font(bold=True, color="FFFFFF", name="Calibri")
    for col in range(1, cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _auto_width(ws):
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)


def render_xlsx(ctx: dict, out: Path):
    wb = openpyxl.Workbook()

    # ── Hoja Resumen ──────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"
    ws.append(["MundoTec — Inventario Activo", "", "", ""])
    ws.merge_cells("A1:D1")
    ws["A1"].font = Font(bold=True, size=16, color=NAVY, name="Trebuchet MS")
    ws.append(["Cliente:", ctx.get("cliente_nombre", "—"), "Fecha:", ctx.get("generado_en", "—")])
    ws.append([])

    resumen = ctx.get("resumen", {})
    ws.append(["Métrica", "Valor"])
    _header_style(ws, ws.max_row, 2)
    for k, v in resumen.items():
        ws.append([k, v])
    _auto_width(ws)

    # ── Hoja Equipos ──────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Equipos")
    cols = ["Nombre", "Tipo", "Marca", "Modelo", "IP Gestión", "Sitio", "Cuarto", "Estado"]
    ws2.append(cols)
    _header_style(ws2, 1, len(cols))
    for eq in ctx.get("equipos", []):
        ws2.append([eq.get(c, "—") for c in
                    ["nombre", "tipo", "marca", "modelo", "ip_gestion", "sitio_nombre", "cuarto_nombre", "estado"]])
    ws2.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"
    _auto_width(ws2)

    # ── Hoja Licencias ────────────────────────────────────────────────────────
    ws3 = wb.create_sheet("Licencias")
    cols3 = ["Producto", "Tipo", "Proveedor", "Vencimiento", "Estado", "Activaciones Max", "Usadas"]
    ws3.append(cols3)
    _header_style(ws3, 1, len(cols3), TEAL)
    for lic in ctx.get("licencias", []):
        ws3.append([lic.get(c, "—") for c in
                    ["producto", "tipo", "proveedor", "fecha_vencimiento", "estado", "activaciones_max", "activaciones_usadas"]])
    _auto_width(ws3)

    # ── Hoja Endpoints ────────────────────────────────────────────────────────
    ws4 = wb.create_sheet("Endpoints")
    cols4 = ["Nombre", "Tipo", "IP", "MAC", "Sitio", "Habitación"]
    ws4.append(cols4)
    _header_style(ws4, 1, len(cols4), AMBER)
    for ep in ctx.get("endpoints", []):
        ws4.append([ep.get(c, "—") for c in
                    ["nombre", "tipo", "ip", "mac", "sitio_nombre", "habitacion"]])
    _auto_width(ws4)

    wb.save(str(out))
