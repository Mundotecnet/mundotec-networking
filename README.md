# MundoTec Networking

Sistema de gestión de infraestructura de red construido con FastAPI + PostgreSQL.

## Requisitos

- Python 3.11+
- PostgreSQL 14+

## Instalación

```bash
cd mundotec-networking

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales de PostgreSQL
```

## Crear la base de datos

```sql
CREATE DATABASE mundotec_networking;
```

## Arrancar el servidor

```bash
uvicorn main:app --reload
```

El servidor queda disponible en `http://localhost:8000`.

- **Frontend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Primer uso

1. Abre http://localhost:8000
2. Haz clic en **Registrarse**
3. Crea el primer usuario con rol **admin**
4. Inicia sesión y comienza a cargar clientes y proyectos

## Estructura del proyecto

| Módulo | Descripción |
|--------|-------------|
| `main.py` | Punto de entrada FastAPI |
| `database.py` | Conexión SQLAlchemy + PostgreSQL |
| `models.py` | Modelos de datos |
| `auth/` | JWT y Google OAuth |
| `routers/` | Endpoints CRUD por recurso |
| `services/` | Lógica de negocio (PDF, diagramas, Excel) |
| `static/` | Frontend SPA (vanilla JS) |

## Importación desde Excel

Los endpoints `/api/projects/{id}/import/devices` y `/api/projects/{id}/import/vlans`
aceptan archivos `.xlsx`. Columnas esperadas:

**Dispositivos**: `room/sala`, `name/nombre`, `type/tipo`, `brand/marca`, `model/modelo`, `ip`, `mac`, `serial`

**VLANs**: `vlan_number/vlan`, `name/nombre`, `subnet/subred`, `gateway`, `description/descripcion`

## Variables de entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | URL PostgreSQL | `postgresql://postgres:postgres@localhost:5432/mundotec_networking` |
| `SECRET_KEY` | Clave JWT (cambiar en producción) | - |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del token | `480` |
| `GOOGLE_CLIENT_ID` | OAuth Google | - |
| `GOOGLE_CLIENT_SECRET` | OAuth Google | - |
| `GOOGLE_REDIRECT_URI` | Callback OAuth | `http://localhost:8000/api/users/google/callback` |
