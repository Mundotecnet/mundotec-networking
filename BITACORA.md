# BITÁCORA TÉCNICA — MundoTec Networking
**Proyecto:** Sistema de gestión de infraestructura de red
**Stack:** FastAPI + PostgreSQL + SPA dark theme (single HTML)
**Servidor:** `mserver` — Ubuntu 22.04 — IP `192.168.88.250`
**Ruta del proyecto:** `/home/lroot/mundotec-networking`
**Entorno de trabajo:** Claude Code corre directamente en el servidor
**Última actualización:** 2026-04-20

---

## FRASES CLAVE DE SESIÓN

| Frase | Acción |
|-------|--------|
| `"iniciamos sesión en networking"` | Leer esta bitácora → contexto cargado |
| `"cierra la sesión"` | Actualizar bitácora + commit |
| `"hacer respaldo"` / `"realiza respaldo"` | Ejecutar `bash /home/lroot/scripts/backup_networking.sh` |

---

## ══ ESTADO ACTUAL ══

### Versión: `v1.0.0` — Inicial

### Acceso
| Servicio | URL | Puerto |
|---------|-----|--------|
| App networking | `http://192.168.88.250:8002` | 8002 |
| API docs | `http://192.168.88.250:8002/docs` | 8002 |
| Health | `http://192.168.88.250:8002/health` | 8002 |

### Credenciales admin
- **Usuario:** `admin`
- **Contraseña:** `Admin123!`

### Base de datos
- **Motor:** PostgreSQL 14
- **BD:** `mundotec_networking`
- **Usuario PG:** `mw_user`
- **Password PG:** `Mw@Web2026!`
- **Host:** `localhost:5432`

---

## ARQUITECTURA

```
/home/lroot/mundotec-networking/
├── main.py                  FastAPI app — routers, search, excel import, startup
├── database.py              Conexión SQLAlchemy + get_db()
├── models.py                Todos los modelos ORM (FK circular con use_alter=True)
├── requirements.txt
├── .env                     Variables de entorno (generadas en primer arranque)
├── auth/
│   ├── jwt.py               Login, get_current_user, require_editor, require_admin
│   └── google.py            OAuth Google — restringido a @mundoteconline.com
├── services/
│   ├── crypto.py            Fernet (credenciales) + bcrypt (contraseñas)
│   ├── audit.py             log() con diff y enmascarado de campos sensibles
│   ├── completeness.py      evaluate_port(), pp_score(), client_analytics()
│   ├── net_diagram.py       Diagramas ReportLab (BFS jerárquico, sin matplotlib)
│   ├── pdf_generator.py     PDF por cliente con credenciales y diagramas
│   └── excel_importer.py    Importación Excel — hoja = cuarto, 24 puertos/panel
├── routers/
│   ├── users.py             CRUD usuarios (admin only)
│   ├── clients.py           Clientes + analytics + PDF report
│   ├── rooms.py             Cuartos anidados bajo clientes
│   ├── patch_panels.py      Paneles — genera 24 puertos automáticamente
│   ├── patch_ports.py       Puertos — validación etiqueta, completitud, confirmación
│   ├── devices.py           Equipos — credenciales Fernet, agrupados activo_red/final
│   ├── device_ports.py      Puertos de equipo — generación automática Gi0/1..N
│   ├── vlans.py             VLANs anidadas bajo cuartos (1-4094)
│   ├── connections.py       Interconexiones polimórficas con chain label
│   ├── backups.py           Archivos de backup por equipo (LargeBinary)
│   ├── audit.py             Log de auditoría con filtros y export CSV
│   └── projects.py          Placeholder — HTTP 501
└── static/
    └── index.html           SPA dark theme completa
```

### Tablas PostgreSQL (`mundotec_networking`)
| Tabla | Descripción |
|-------|-------------|
| `users` | Usuarios locales y Google OAuth |
| `clients` | Clientes de Mundotec |
| `rooms` | Cuartos de red por cliente |
| `vlans` | VLANs por cuarto (id real 1-4094) |
| `patch_panels` | Paneles de parcheo por cuarto |
| `patch_ports` | Puertos de panel (24 por panel, completitud) |
| `devices` | Equipos activos (credenciales Fernet) |
| `device_ports` | Puertos de equipos activos |
| `connections` | Interconexiones polimórficas |
| `backup_files` | Archivos de configuración por equipo |
| `audit_logs` | Registro de auditoría completo |
| `projects` | Placeholder proyectos (futuro) |
| `project_logs` | Placeholder logs proyectos (futuro) |

### Roles de usuario
| Rol | Permisos |
|-----|---------|
| `admin` | Todo — usuarios, auditoría, eliminar |
| `tecnico` | Crear y editar (require_editor) |
| `readonly` | Solo lectura |

---

## PROTOCOLO DE DEPLOY

```bash
# 1. Editar archivos en /home/lroot/mundotec-networking/
# 2. Commit
git add <archivos>
git commit -m "tipo: descripción breve"

# 3. Reiniciar si es necesario (actualmente manual con nohup)
pkill -f "uvicorn main:app.*8002" || true
nohup uvicorn main:app --host 0.0.0.0 --port 8002 > /tmp/mundotec-networking.log 2>&1 &
```

---

## SISTEMA DE RESPALDO

```
/home/lroot/backups/                          ← Local (retención 14 días)
    ├── mundotec-networking.git/              Bare repo — historial git permanente
    ├── networking_git_FECHA.bundle           Snapshot git diario
    └── networking_db_FECHA.sql.gz            Base de datos PostgreSQL

/mnt/backup-ext/MUNDOTEC/backups-servidor/    ← Disco externo NTFS 932 GB
    └── (copia de todos los archivos anteriores)
```

### Archivos generados
| Archivo | Contenido | Retención |
|---------|-----------|-----------|
| `mundotec-networking.git/` | Bare repo — historial git completo | Permanente |
| `networking_git_FECHA.bundle` | Snapshot portátil del historial | 14 días |
| `networking_db_FECHA.sql.gz` | Base de datos PostgreSQL completa | 14 días |

### Scripts
| Script | Función | Cron |
|--------|---------|------|
| `backup_networking.sh` | Git + PostgreSQL | 02:15 AM diario |

### Log
`/home/lroot/backups/backup_networking.log`

---

## PROTOCOLO DE RESPALDO

```bash
# Respaldo manual
bash /home/lroot/scripts/backup_networking.sh

# Verificar último respaldo
tail -20 /home/lroot/backups/backup_networking.log
```

---

## GOTCHAS / ADVERTENCIAS

1. **FK circular**: `PatchPort.switch_port_id` → `DevicePort` y `DevicePort.patch_port_id` → `PatchPort` resuelto con `use_alter=True` en models.py.
2. **Credenciales Fernet**: `username_encrypted` y `password_encrypted` en `Device`. Se generan con `FERNET_KEY` del `.env` — si la key cambia, las credenciales existentes no se pueden descifrar.
3. **SECRET_KEY y FERNET_KEY**: Se auto-generan en el primer arranque y se guardan en `.env`. No eliminar.
4. **Google OAuth**: Deshabilitado por defecto (`GOOGLE_AUTH_ENABLED=false`). Solo permite `@mundoteconline.com`. Nuevos usuarios quedan `is_active=False` hasta activación manual por admin.
5. **Completitud puertos**: Sin revisar → completo requiere MAC + IP + VLAN + (switch_port si hay switch en el cuarto).
6. **Excel import**: Cada hoja = un cuarto. Siempre genera exactamente 24 puertos por panel.
7. **PDF**: Solo ReportLab — sin matplotlib ni networkx.
8. **Arranque actual**: `nohup uvicorn main:app --host 0.0.0.0 --port 8002` (sin systemd aún).

---

## BACKUPS

| Fecha | Tipo | Descripción |
|-------|------|-------------|
| 2026-04-20 | Git inicial | v1.0.0 — Primera versión funcional completa |

---

## BITÁCORA DE CAMBIOS

### [SESIÓN 1] — 2026-04-20 — Implementación inicial + puesta en marcha

| # | Tipo | Descripción |
|---|------|-------------|
| 1 | Nuevo | Proyecto `mundotec-networking` creado con estructura completa |
| 2 | Nuevo | PostgreSQL — BD `mundotec_networking` (usuario compartido `mw_user`) |
| 3 | Nuevo | 13 tablas: users, clients, rooms, vlans, patch_panels, patch_ports, devices, device_ports, connections, backup_files, audit_logs, projects, project_logs |
| 4 | Nuevo | Auth JWT (usuario/contraseña) + Google OAuth restringido a @mundoteconline.com |
| 5 | Nuevo | Fernet encryption para credenciales de equipos |
| 6 | Nuevo | SPA dark theme — IBM Plex Sans, sidebar 220px, 8 páginas |
| 7 | Nuevo | Importación Excel (hoja = cuarto, 24 puertos/panel auto-generados) |
| 8 | Nuevo | PDF por cliente con diagramas ReportLab y sección de credenciales |
| 9 | Nuevo | Sistema de auditoría completo con diff y export CSV |
| 10 | Infra | Servidor en puerto 8002 con `nohup uvicorn` |
| 11 | Infra | Git repo inicializado + primer commit |
| 12 | Infra | Script `backup_networking.sh` — Git + PostgreSQL → local + disco externo |
| 13 | Fix | `@` en password URL-encoded (`%40`) para DATABASE_URL en SQLAlchemy |

---
*Actualizar esta bitácora al cierre de cada sesión con `"cierra la sesión"`*
