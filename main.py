"""
MundoTec Networking — punto de entrada principal.
Arrancar con: uvicorn main:app --reload
"""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Auto-generate missing keys ────────────────────────────────────────────────
_env_path = Path(".env")
_changed = False

if not os.getenv("SECRET_KEY"):
    _key = secrets.token_hex(32)
    os.environ["SECRET_KEY"] = _key
    if _env_path.exists():
        with open(_env_path, "a") as _f:
            _f.write(f"\nSECRET_KEY={_key}\n")
    _changed = True

if not os.getenv("FERNET_KEY"):
    from cryptography.fernet import Fernet as _F
    _fk = _F.generate_key().decode()
    os.environ["FERNET_KEY"] = _fk
    if _env_path.exists():
        with open(_env_path, "a") as _f:
            _f.write(f"FERNET_KEY={_fk}\n")
    _changed = True

# ── App setup ─────────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from database import engine
import models

models.Base.metadata.create_all(bind=engine)

from auth import jwt as auth_jwt
from auth import google as auth_google
from routers import (
    users, clients, rooms, buildings, cabinets, patch_panels, patch_ports,
    devices, device_ports, vlans, connections, backups,
    audit as audit_router, projects,
    sitios, edificios, cuartos, gabinetes,
    trazabilidad,
    ipam, fibra, credenciales,
    reportes,
    conexiones_directas,
)

app = FastAPI(
    title="MundoTec Networking",
    description="Sistema de gestión de infraestructura de red",
    version="1.0.0",
)

# CORS
_allowed_origin = os.getenv("ALLOWED_ORIGIN", "http://localhost:8002")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8002", _allowed_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = "/api"
for r in [
    auth_jwt.router,
    auth_google.router,
    users.router,
    clients.router,
    buildings.router,
    rooms.router,
    cabinets.router,
    patch_panels.router,
    patch_ports.router,
    devices.router,
    device_ports.router,
    vlans.router,
    connections.router,
    backups.router,
    audit_router.router,
    projects.router,
    sitios.router,
    edificios.router,
    cuartos.router,
    gabinetes.router,
    trazabilidad.router,
    ipam.router,
    fibra.router,
    credenciales.router,
    reportes.router,
    conexiones_directas.router,
]:
    app.include_router(r, prefix=PREFIX)

# ── Search endpoint ───────────────────────────────────────────────────────────
from fastapi import Depends, Query as QParam
from sqlalchemy.orm import Session
from database import get_db
from auth.jwt import get_current_user


@app.get("/api/search")
def search(
    q: str = QParam(..., min_length=2),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    from services.busqueda import buscar
    return buscar(q, db)


# ── Excel import endpoint ─────────────────────────────────────────────────────
from fastapi import UploadFile, File, Form
from services.excel_importer import import_excel, preview_excel, import_into_panel, verify_import
from services import audit as audit_svc
from auth.jwt import require_editor


@app.post("/api/import/excel")
async def import_excel_endpoint(
    request: Request,
    file: UploadFile = File(...),
    client_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    content = await file.read()
    result = import_excel(db, content, client_name, current_user)
    audit_svc.log(
        db, "IMPORT_EXCEL", "client",
        entity_label=client_name,
        notes=f"rooms={result['rooms_created']} ports={result['ports_imported']}",
        user=current_user, request=request,
    )
    return result


@app.post("/api/import/preview")
async def preview_excel_endpoint(
    file: UploadFile = File(...),
    _: models.User = Depends(require_editor),
):
    content = await file.read()
    return preview_excel(content)


@app.post("/api/import/verify/{pp_id}")
async def verify_import_endpoint(
    pp_id: int,
    file: UploadFile = File(...),
    sheet_index: int = Form(0),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_editor),
):
    content = await file.read()
    try:
        return verify_import(db, content, pp_id, sheet_index)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/import/into-panel/{pp_id}")
async def import_into_panel_endpoint(
    pp_id: int,
    request: Request,
    file: UploadFile = File(...),
    sheet_index: int = Form(0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    content = await file.read()
    try:
        result = import_into_panel(db, content, pp_id, sheet_index, current_user)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    audit_svc.log(
        db, "IMPORT_EXCEL", "patch_panel", entity_id=pp_id,
        entity_label=result["panel_name"],
        notes=f"sheet={result['sheet_name']} ports_updated={result['ports_updated']}",
        user=current_user, request=request,
    )
    return result


# ── Static & SPA ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "mundotec-networking", "version": "1.0.0"}


# ── Exception handlers ────────────────────────────────────────────────────────
from fastapi import HTTPException


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exc_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Startup: create default admin ─────────────────────────────────────────────
@app.on_event("startup")
def create_default_admin():
    from database import SessionLocal
    from services.crypto import hash_pw
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            admin = models.User(
                username="admin",
                full_name="Administrador",
                hashed_password=hash_pw("Admin123!"),
                role="admin",
                auth_provider="local",
                is_active=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
