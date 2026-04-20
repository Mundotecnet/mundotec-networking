from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_admin
from services.crypto import hash_pw
from services import audit as audit_svc

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str
    role: str = "readonly"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    auth_provider: str
    is_active: bool
    google_email: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    return db.query(models.User).order_by(models.User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Nombre de usuario ya existe")
    user = models.User(
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_pw(payload.password),
        role=payload.role,
        auth_provider="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_svc.log(db, "CREATE", "user", entity_id=user.id, entity_label=user.username,
                  user=current_user, request=request,
                  new_values={"username": user.username, "role": user.role})
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, payload: UserUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    old = {"role": user.role, "is_active": user.is_active}
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        user.hashed_password = hash_pw(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    audit_svc.log(db, "UPDATE", "user", entity_id=user.id, entity_label=user.username,
                  old_values=old, new_values=data, user=current_user, request=request)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    audit_svc.log(db, "DELETE", "user", entity_id=user.id, entity_label=user.username,
                  user=current_user, request=request)
    db.delete(user)
    db.commit()
    return {"message": "Usuario eliminado"}


@router.put("/users/{user_id}/activate")
def activate_user(
    user_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = True
    db.commit()
    audit_svc.log(db, "GOOGLE_USER_ACTIVATED", "user", entity_id=user.id,
                  entity_label=user.username, user=current_user, request=request)
    return {"message": "Usuario activado"}
