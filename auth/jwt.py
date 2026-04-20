from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os

from database import get_db
import models
from services.crypto import hash_pw, verify_pw
from services import audit as audit_svc

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8
GOOGLE_AUTH_ENABLED = os.getenv("GOOGLE_AUTH_ENABLED", "false").lower() == "true"
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "mundoteconline.com")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Utilities ─────────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise exc
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return user


def require_editor(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role not in ("admin", "tecnico"):
        raise HTTPException(status_code=403, detail="Se requieren permisos de editor")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Se requieren permisos de administrador")
    return user


# ── Schemas ───────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserMe(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    auth_provider: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or user.auth_provider != "local" or not user.hashed_password:
        audit_svc.log(db, "LOGIN_REJECTED_DOMAIN", "user", notes=form_data.username, request=request)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    if not verify_pw(form_data.password, user.hashed_password):
        audit_svc.log(db, "LOGIN_REJECTED_DOMAIN", "user", notes=form_data.username, request=request)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    token = create_access_token({"sub": user.username})
    audit_svc.log(db, "LOGIN", "user", entity_id=user.id, entity_label=user.username,
                  user=user, request=request)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "full_name": user.full_name,
                 "role": user.role, "auth_provider": user.auth_provider},
    }


@router.get("/auth/me", response_model=UserMe)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("/auth/config")
def auth_config():
    return {
        "google_auth_enabled": GOOGLE_AUTH_ENABLED,
        "allowed_domain": ALLOWED_DOMAIN,
    }
