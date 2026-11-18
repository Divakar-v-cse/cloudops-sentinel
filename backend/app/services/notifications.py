"""In-app notifications (SNS-compatible payload shape for optional fan-out)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Notification


def notify(
    db: Session,
    *,
    title: str,
    message: str,
    severity: str = "info",
    category: str = "system",
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    commit: bool = True,
) -> Notification:
    item = Notification(
        title=title[:200],
        message=message,
        severity=severity,
        category=category,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )
    db.add(item)
    if commit:
        db.commit()
        db.refresh(item)
    return item


def recent(db: Session, limit: int = 10) -> list[Notification]:
    return (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def serialise(item: Notification) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "message": item.message,
        "severity": item.severity,
        "category": item.category,
        "is_read": item.is_read,
        "created_at": item.created_at,
    }
