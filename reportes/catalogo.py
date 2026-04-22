"""Catálogo de los 6 tipos de informe — sub-tarea 2.2."""
from .base import ReporteBase


class ReporteInfraestructura(ReporteBase):
    titulo = "Informe de Infraestructura Actual"
    plantilla = "infraestructura.html"
    formato_default = "pdf"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_infra import construir
        ctx = construir(
            self.db, self.cliente_id,
            sitios=self.params.get("sitios", "all"),
            incluir_credenciales=self.params.get("incluir_credenciales", False),
        )
        ctx["subtitulo"] = f"Sitios: {ctx['total_sitios']} · Equipos: {ctx['total_equipos']}"
        ctx["secciones"] = ["Resumen Ejecutivo"] + \
            [f"Sitio: {s['nombre']}" for s in ctx.get("sitios", [])] + \
            (["Anexo A — Licencias"] if ctx.get("licencias") else []) + \
            (["Anexo B — Credenciales"] if ctx.get("credenciales") else [])
        return ctx


class ReporteTrazabilidad(ReporteBase):
    titulo = "Informe de Trazabilidad por Endpoint"
    plantilla = "trazabilidad.html"
    formato_default = "pdf"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_trazabilidad import construir
        ctx = construir(
            self.db, self.cliente_id,
            endpoint_id=self.params.get("endpoint_id"),
        )
        ctx["subtitulo"] = f"{ctx['total']} endpoint(s) documentados"
        ctx["secciones"] = [f"Endpoint: {ep['nombre']}" for ep in ctx.get("endpoints", [])]
        return ctx


class ReporteMantenimiento(ReporteBase):
    titulo = "Mantenimiento Preventivo Trimestral"
    plantilla = "mantenimiento.html"
    formato_default = "pdf"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_mantenimiento import construir
        ctx = construir(self.db, self.cliente_id)
        ctx["subtitulo"] = "Checklist de mantenimiento y recomendaciones"
        ctx["secciones"] = ["Licencias por Vencer", "Recomendaciones", "Inventario de Equipos"]
        return ctx


class ReporteEjecutivo(ReporteBase):
    titulo = "Informe Ejecutivo Mensual"
    plantilla = "ejecutivo.html"
    formato_default = "pdf"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_infra import construir
        ctx = construir(self.db, self.cliente_id)
        from reportes.datos.builder_mantenimiento import construir as construir_mant
        mant = construir_mant(self.db, self.cliente_id)
        ctx["subtitulo"] = "Resumen para dirección"
        ctx["alertas"] = []
        ctx["recomendaciones"] = mant.get("recomendaciones", [])
        ctx["licencias_por_vencer"] = len(mant.get("licencias_por_vencer", []))
        return ctx


class ReporteInventario(ReporteBase):
    titulo = "Inventario Activo"
    plantilla = "inventario_xlsx.html"
    formato_default = "xlsx"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_inventario import construir
        return construir(self.db, self.cliente_id)

    def generar(self):
        from reportes.base import STORAGE
        from reportes.render_xlsx import render_xlsx
        from pathlib import Path
        import yaml
        from reportes.base import BRANDING_FILE
        with open(BRANDING_FILE) as f:
            branding = yaml.safe_load(f)
        from datetime import datetime
        STORAGE.mkdir(parents=True, exist_ok=True)
        ctx = self.construir_contexto()
        ctx["branding"] = branding
        ctx["generado_en"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        ctx["reporte_id"] = self.reporte_id
        out = STORAGE / f"{self.reporte_id}.xlsx"
        render_xlsx(ctx, out)
        return out


class ReportePostMortem(ReporteBase):
    titulo = "Post-Mortem de Incidente"
    plantilla = "postmortem.html"
    formato_default = "pdf"

    def construir_contexto(self) -> dict:
        from reportes.datos.builder_infra import construir
        ctx = construir(self.db, self.cliente_id)
        ctx.update({
            "subtitulo": self.params.get("incidente_titulo", "Incidente sin título"),
            "incidente_titulo": self.params.get("incidente_titulo", "—"),
            "inicio": self.params.get("inicio", "—"),
            "duracion": self.params.get("duracion", "—"),
            "impacto": self.params.get("impacto", "—"),
            "severidad": self.params.get("severidad", "—"),
            "rca": self.params.get("rca", "Por determinar."),
            "remediacion": self.params.get("remediacion", "Por documentar."),
            "accion_correctiva": self.params.get("accion_correctiva", "Por definir."),
            "timeline": self.params.get("timeline", []),
        })
        return ctx


CATALOGO = {
    "infraestructura": ReporteInfraestructura,
    "trazabilidad": ReporteTrazabilidad,
    "mantenimiento": ReporteMantenimiento,
    "ejecutivo": ReporteEjecutivo,
    "inventario": ReporteInventario,
    "postmortem": ReportePostMortem,
}
