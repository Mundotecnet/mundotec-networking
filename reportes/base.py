"""Motor base de generación de reportes — MundoTec."""
from __future__ import annotations
import os, uuid, hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

STORAGE = Path(os.getenv("REPORTES_DIR", "storage/reportes"))
TEMPLATES_DIR = Path(__file__).parent / "templates"
BRANDING_FILE = Path(__file__).parent / "branding.yaml"

_jinja = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _load_branding() -> dict:
    with open(BRANDING_FILE) as f:
        return yaml.safe_load(f)


class ReporteBase:
    titulo: str = "Informe"
    plantilla: str = "base.html"
    formato_default: str = "pdf"

    def __init__(self, cliente_id, formato: str = "pdf", params: Optional[dict] = None,
                 db=None, usuario=None):
        self.cliente_id = cliente_id
        self.formato = formato
        self.params = params or {}
        self.db = db
        self.usuario = usuario
        self.reporte_id = str(uuid.uuid4())
        self.branding = _load_branding()

    def construir_contexto(self) -> dict:
        """Subclases deben sobreescribir este método."""
        return {}

    def nombre_archivo(self, ctx: dict) -> str:
        slug = ctx.get("cliente_nombre", "cliente").replace(" ", "_")[:30]
        fecha = datetime.now().strftime("%Y%m%d")
        return f"{self.titulo.replace(' ', '_')}_{slug}_{fecha}"

    def generar(self) -> Path:
        STORAGE.mkdir(parents=True, exist_ok=True)
        ctx = self.construir_contexto()
        ctx["branding"] = self.branding
        ctx["generado_en"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        ctx["reporte_id"] = self.reporte_id
        ctx["titulo"] = self.titulo

        if self.formato == "pdf":
            return self._generar_pdf(ctx)
        elif self.formato == "xlsx":
            return self._generar_xlsx(ctx)
        elif self.formato == "docx":
            return self._generar_docx(ctx)
        else:
            raise ValueError(f"Formato no soportado: {self.formato}")

    def _generar_pdf(self, ctx: dict) -> Path:
        from weasyprint import HTML, CSS
        tmpl = _jinja.get_template(self.plantilla)
        html_str = tmpl.render(**ctx)
        out = STORAGE / f"{self.reporte_id}.pdf"
        css_path = TEMPLATES_DIR / "estilos.css"
        stylesheets = [CSS(filename=str(css_path))] if css_path.exists() else []
        HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf(
            str(out), stylesheets=stylesheets
        )
        return out

    def _generar_xlsx(self, ctx: dict) -> Path:
        from reportes.render_xlsx import render_xlsx
        out = STORAGE / f"{self.reporte_id}.xlsx"
        render_xlsx(ctx, out)
        return out

    def _generar_docx(self, ctx: dict) -> Path:
        from docxtpl import DocxTemplate
        tmpl_path = TEMPLATES_DIR / self.plantilla.replace(".html", ".docx")
        if not tmpl_path.exists():
            raise FileNotFoundError(f"Template DOCX no encontrado: {tmpl_path}")
        doc = DocxTemplate(str(tmpl_path))
        doc.render(ctx)
        out = STORAGE / f"{self.reporte_id}.docx"
        doc.save(str(out))
        return out
