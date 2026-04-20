import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import get_db
import models
from auth.jwt import require_admin

router = APIRouter()


class AuditOut(BaseModel):
    id: int
    timestamp: Optional[datetime]
    user_id: Optional[int]
    user_name: Optional[str]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    entity_label: Optional[str]
    client_id: Optional[int]
    old_values: Optional[dict]
    new_values: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    notes: Optional[str]

    model_config = {"from_attributes": True}


@router.get("/audit", response_model=List[AuditOut])
def list_audit(
    skip: int = 0,
    limit: int = Query(100, le=1000),
    client_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    q = db.query(models.AuditLog)
    if client_id:
        q = q.filter(models.AuditLog.client_id == client_id)
    if entity_type:
        q = q.filter(models.AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(models.AuditLog.action == action)
    if user_id:
        q = q.filter(models.AuditLog.user_id == user_id)
    if search:
        q = q.filter(
            models.AuditLog.entity_label.ilike(f"%{search}%") |
            models.AuditLog.user_name.ilike(f"%{search}%") |
            models.AuditLog.notes.ilike(f"%{search}%")
        )
    if date_from:
        try:
            q = q.filter(models.AuditLog.timestamp >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(models.AuditLog.timestamp <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    return q.order_by(models.AuditLog.timestamp.desc()).offset(skip).limit(limit).all()


@router.get("/audit/entity/{entity_type}/{entity_id}", response_model=List[AuditOut])
def audit_for_entity(
    entity_type: str, entity_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    return (
        db.query(models.AuditLog)
        .filter(
            models.AuditLog.entity_type == entity_type,
            models.AuditLog.entity_id == entity_id,
        )
        .order_by(models.AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )


@router.get("/audit/export")
def export_audit_csv(
    client_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    q = db.query(models.AuditLog)
    if client_id:
        q = q.filter(models.AuditLog.client_id == client_id)
    logs = q.order_by(models.AuditLog.timestamp.desc()).limit(5000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Timestamp", "Usuario", "Acción", "Entidad", "ID Entidad",
                     "Etiqueta", "Cliente ID", "IP", "Notas"])
    for entry in logs:
        writer.writerow([
            entry.id,
            entry.timestamp.isoformat() if entry.timestamp else "",
            entry.user_name or "",
            entry.action,
            entry.entity_type or "",
            entry.entity_id or "",
            entry.entity_label or "",
            entry.client_id or "",
            entry.ip_address or "",
            entry.notes or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv"},
    )
