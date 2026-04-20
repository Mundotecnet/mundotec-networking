from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from sqlalchemy.orm import Session
import models

if TYPE_CHECKING:
    from fastapi import Request

SENSITIVE_FIELDS = {
    "hashed_password", "username_encrypted", "password_encrypted", "file_content"
}


def _sanitize(values: dict | None) -> dict | None:
    if not values:
        return values
    return {
        k: "[CIFRADO]" if k in SENSITIVE_FIELDS else v
        for k, v in values.items()
    }


def log(
    db: Session,
    action: str,
    entity_type: str = "",
    entity_id: int | None = None,
    entity_label: str = "",
    client_id: int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    notes: str = "",
    user: Optional["models.User"] = None,
    request: Optional[Any] = None,
) -> None:
    ip = None
    ua = None
    if request is not None:
        try:
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent", "")
        except Exception:
            pass

    entry = models.AuditLog(
        user_id=user.id if user else None,
        user_name=user.username if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        client_id=client_id,
        old_values=_sanitize(old_values),
        new_values=_sanitize(new_values),
        ip_address=ip,
        user_agent=ua,
        notes=notes,
    )
    db.add(entry)
    db.commit()
