---
name: Estado del proyecto mundotec-networking
description: Arquitectura completa, rutas, módulos, sprints completados y gotchas del proyecto
type: project
---

# mundotec-networking — Estado completo

**Stack:** FastAPI + PostgreSQL 14 + SPA dark theme (single HTML)
**Servidor:** `mserver` — Ubuntu 22.04 — IP `192.168.88.250`
**Ruta:** `/home/lroot/mundotec-networking/`
**Puerto:** 8002
**Servicio systemd:** `mundotec-networking.service`
**BD:** `mundotec_networking` — usuario `mw_user` / password `Mw@Web2026!`

## Credenciales admin
- usuario: `admin` / contraseña: `Admin123!`
- Auth: JWT form-urlencoded POST `/api/auth/login`
- Google OAuth disponible pero deshabilitado por defecto

## Sprints completados (commits en main)
1. **v1.0.0 inicial** — modelos, auth JWT+Google, SPA dark theme, import Excel, PDF ReportLab, auditoría
2. **fix restaurar routers/seed** — archivos tenían output de git en lugar de código
3. **Etapa 1** — multi-sitio, IPAM, fibra óptica, credenciales Fernet, trazabilidad de endpoints, búsqueda global
4. **Sprint 5** — motor de reportes PDF/XLSX: 6 tipos, templates WeasyPrint, historial, polling estado

## Estructura de archivos clave
```
main.py                  — FastAPI app, routers, search, excel import, startup (crea admin si BD vacía)
database.py              — SQLAlchemy + get_db()
models.py                — ORM completo (FK circular resuelta con use_alter=True)
auth/jwt.py              — login, get_current_user, require_editor, require_admin
auth/google.py           — OAuth Google restringido a @mundoteconline.com
services/crypto.py       — hash_pw()/verify_pw() bcrypt + encrypt()/decrypt() Fernet
services/audit.py        — log() con diff automático
services/completeness.py — evaluate_port(), pp_score(), client_analytics()
routers/                 — clients, rooms, vlans, patch_panels, patch_ports, devices,
                           device_ports, connections, backups, audit, sitios, edificios,
                           cuartos, gabinetes, ipam, fibra, credenciales, trazabilidad,
                           reportes, users, projects
reportes/                — base.py, catalogo.py, render_xlsx.py, branding.yaml, datos/, templates/
static/index.html        — SPA completa (todo el frontend en un solo archivo)
```

## Tablas PostgreSQL
users, clients, rooms, vlans, patch_panels, patch_ports, devices, device_ports,
connections, backup_files, audit_logs, projects, project_logs,
sitios, edificios, cuartos, gabinetes, nodos_fibra, tramos_fibra,
credencial, ipam_vlan, audit_log

## Gotchas críticos
1. **FK circular** PatchPort↔DevicePort — resuelto con `use_alter=True` en models.py. NO tocar.
2. **FERNET_KEY** en `.env` — si cambia, las credenciales cifradas existentes quedan irrecuperables.
3. **SECRET_KEY y FERNET_KEY** se auto-generan al primer arranque en `.env`. No borrar `.env`.
4. **Contraseña admin**: solo se crea automáticamente si la BD está vacía (`count()==0`). Si ya hay users, hay que resetear manualmente con `services.crypto.hash_pw`.
5. **SPA static**: `static/index.html` es servido por FastAPI StaticFiles — se actualiza en disco sin reiniciar uvicorn.
6. **JS bug resuelto 2026-04-22**: Sprint 5 introdujo `let _impFile = null;` duplicado (línea 731 y 1598 del HTML). Causaba SyntaxError que rompía todo el JS incluyendo el login. Eliminado el de línea 731.
7. **PDF**: usa ReportLab (no matplotlib, no networkx). Para reportes WeasyPrint necesita `libpango`.
8. **Excel import**: cada hoja = un cuarto, genera exactamente 24 puertos por panel.

## Protocolo deploy
```bash
# Editar en /home/lroot/mundotec-networking/
git add <archivos> && git commit -m "tipo: descripción"
sudo systemctl restart mundotec-networking.service
```

## Frases clave de sesión
- `"iniciamos sesión en networking"` → leer BITACORA.md para contexto detallado
- `"cierra la sesión"` → actualizar bitácora + commit + push
- `"hacer respaldo"` → `bash /home/lroot/scripts/backup_networking.sh`

**Why:** El proyecto pierde contexto entre conversaciones causando regresiones y trabajo duplicado.
**How to apply:** Leer esta memoria al inicio de CUALQUIER sesión de mundotec-networking antes de tocar código.
