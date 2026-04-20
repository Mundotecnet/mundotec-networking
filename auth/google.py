import os
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
import models
from auth.jwt import create_access_token, GOOGLE_AUTH_ENABLED, ALLOWED_DOMAIN
from services import audit as audit_svc

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/auth/google/login")
def google_login():
    if not GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Google Auth no está habilitado")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "hd": ALLOWED_DOMAIN,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{AUTH_URL}?{urlencode(params)}")


@router.get("/auth/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    if not GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Google Auth no está habilitado")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Error al obtener token de Google")
        access_token = token_resp.json().get("access_token")

        user_resp = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Error al obtener datos de Google")
        g = user_resp.json()

    email: str = g.get("email", "")
    domain = email.split("@")[-1] if "@" in email else ""
    if domain != ALLOWED_DOMAIN:
        audit_svc.log(db, "LOGIN_REJECTED_DOMAIN", "user", notes=email)
        raise HTTPException(status_code=403, detail=f"Dominio @{domain} no permitido")

    user = db.query(models.User).filter(models.User.google_id == g["id"]).first()
    if not user:
        user = db.query(models.User).filter(models.User.google_email == email).first()

    if not user:
        username = email.split("@")[0]
        base = username
        suffix = 1
        while db.query(models.User).filter(models.User.username == username).first():
            username = f"{base}{suffix}"
            suffix += 1
        user = models.User(
            username=username,
            full_name=g.get("name", email),
            role="readonly",
            auth_provider="google",
            google_id=g["id"],
            google_email=email,
            google_picture=g.get("picture"),
            google_name=g.get("name"),
            is_active=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        audit_svc.log(db, "GOOGLE_USER_CREATED", "user", entity_id=user.id,
                      entity_label=user.username)
        return RedirectResponse(url="/?google_pending=1")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario pendiente de activación por el administrador")

    if not user.google_id:
        user.google_id = g["id"]
    user.google_picture = g.get("picture")
    user.google_name = g.get("name")
    db.commit()

    token = create_access_token({"sub": user.username})
    audit_svc.log(db, "LOGIN_GOOGLE", "user", entity_id=user.id, entity_label=user.username)
    return RedirectResponse(url=f"/?token={token}")
