import os
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor
from services import audit as audit_svc

router = APIRouter()

MAX_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))


class BackupOut(BaseModel):
    id: int
    device_id: int
    filename: str
    file_size: int
    version: Optional[str]
    notes: Optional[str]
    uploaded_by: Optional[int]

    model_config = {"from_attributes": True}


@router.get("/devices/{device_id}/backups", response_model=List[BackupOut])
def list_backups(device_id: int, db: Session = Depends(get_db),
                 _: models.User = Depends(get_current_user)):
    if not db.query(models.Device).filter(models.Device.id == device_id).first():
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return (
        db.query(models.BackupFile)
        .filter(models.BackupFile.device_id == device_id)
        .order_by(models.BackupFile.uploaded_at.desc())
        .all()
    )


@router.post("/devices/{device_id}/backups", response_model=BackupOut, status_code=201)
async def upload_backup(
    device_id: int,
    request: Request,
    file: UploadFile = File(...),
    version: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx. {MAX_SIZE // 1024 // 1024} MB)")
    b = models.BackupFile(
        device_id=device_id,
        filename=file.filename or f"backup_{device_id}.txt",
        file_content=content,
        file_size=len(content),
        version=version,
        notes=notes,
        uploaded_by=current_user.id,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    audit_svc.log(db, "DOWNLOAD_BACKUP", "backup", entity_id=b.id, entity_label=b.filename,
                  client_id=device.room.client_id, user=current_user, request=request)
    return b


@router.get("/backups/{backup_id}/download")
def download_backup(
    backup_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    b = db.query(models.BackupFile).filter(models.BackupFile.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    audit_svc.log(db, "DOWNLOAD_BACKUP", "backup", entity_id=b.id, entity_label=b.filename,
                  client_id=b.device.room.client_id, user=current_user, request=request)
    return Response(
        content=b.file_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{b.filename}"'},
    )


@router.delete("/backups/{backup_id}")
def delete_backup(
    backup_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    b = db.query(models.BackupFile).filter(models.BackupFile.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    audit_svc.log(db, "DELETE", "backup", entity_id=b.id, entity_label=b.filename,
                  client_id=b.device.room.client_id, user=current_user, request=request)
    db.delete(b)
    db.commit()
    return {"message": "Backup eliminado"}
