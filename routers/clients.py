from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
import models
from auth.jwt import get_current_user, require_editor, require_admin
from services import audit as audit_svc
from services.completeness import client_analytics
from services.pdf_generator import generate_client_report

router = APIRouter()


LABEL_FORMATS = {"simple", "full", "extended", "edificio_cuarto_rack"}


class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    label_format: Optional[str] = "edificio_cuarto_rack"


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    label_format: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    contact: Optional[str]
    notes: Optional[str]
    label_format: Optional[str] = "edificio_cuarto_rack"

    model_config = {"from_attributes": True}


class ClientSummary(ClientOut):
    room_count: int = 0
    port_count: int = 0
    score: float = 0.0


@router.get("/clients", response_model=List[ClientSummary])
def list_clients(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    clients = db.query(models.Client).order_by(models.Client.name).all()
    result = []
    for c in clients:
        port_count = sum(len(pp.ports) for r in c.rooms for pp in r.patch_panels)
        try:
            analytics = client_analytics(c)
            score = analytics["score"]
        except Exception:
            score = 0.0
        result.append(ClientSummary(
            id=c.id, name=c.name, phone=c.phone, email=c.email,
            address=c.address, contact=c.contact, notes=c.notes,
            room_count=len(c.rooms), port_count=port_count, score=score,
        ))
    return result


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db),
               _: models.User = Depends(get_current_user)):
    c = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return c


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = models.Client(**payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, "CREATE", "client", entity_id=c.id, entity_label=c.name,
                  client_id=c.id, user=current_user, request=request,
                  new_values=payload.model_dump())
    return c


@router.put("/clients/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int, payload: ClientUpdate, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_editor),
):
    c = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    old = {k: getattr(c, k) for k in payload.model_dump().keys()}
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, "UPDATE", "client", entity_id=c.id, entity_label=c.name,
                  client_id=c.id, old_values=old, new_values=payload.model_dump(exclude_unset=True),
                  user=current_user, request=request)
    return c


@router.delete("/clients/{client_id}")
def delete_client(
    client_id: int, request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    c = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    audit_svc.log(db, "DELETE", "client", entity_id=c.id, entity_label=c.name,
                  client_id=c.id, user=current_user, request=request)
    db.delete(c)
    db.commit()
    return {"message": "Cliente eliminado"}


@router.get("/clients/{client_id}/analytics")
def get_analytics(client_id: int, db: Session = Depends(get_db),
                  _: models.User = Depends(get_current_user)):
    c = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return client_analytics(c)


@router.get("/clients/{client_id}/report.pdf")
def client_pdf(
    client_id: int, request: Request,
    include_changes: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        pdf = generate_client_report(db, client_id, include_recent_changes=include_changes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    audit_svc.log(db, "EXPORT_PDF", "client", entity_id=client_id,
                  client_id=client_id, user=current_user, request=request)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cliente_{client_id}.pdf"},
    )
