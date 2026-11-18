"""Audit log, notifications, settings and dashboard endpoints."""
from __future__ import annotations

import importlib.util
import math
import shutil

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, text

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.config import settings as app_settings
from app.models import AuditLog, Notification, Setting
from app.schemas.common import Paginated
from app.schemas.domain import AuditOut, NotificationOut
from app.services import dashboard as dashboard_service
from app.services.audit import record_audit
from app.services.logs import retention_cleanup

router = APIRouter(tags=["platform"])


# ------------------------------------------------------------------ audit
@router.get("/audit", response_model=Paginated[AuditOut])
def audit_logs(
    db: DbSession,
    user: CurrentUser,
    action: str | None = None,
    entity_type: str | None = None,
    actor: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Paginated[AuditOut]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(AuditLog.action.ilike(like), AuditLog.entity_id.ilike(like)))
    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Paginated[AuditOut](
        items=[AuditOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/audit/facets")
def audit_facets(db: DbSession, user: CurrentUser) -> dict:
    actions = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(30)
        .all()
    )
    entities = (
        db.query(AuditLog.entity_type, func.count(AuditLog.id))
        .group_by(AuditLog.entity_type)
        .order_by(func.count(AuditLog.id).desc())
        .all()
    )
    return {
        "actions": [{"action": a, "count": c} for a, c in actions],
        "entity_types": [{"entity_type": e, "count": c} for e, c in entities],
        "total": db.query(func.count(AuditLog.id)).scalar() or 0,
    }


# ----------------------------------------------------------- notifications
@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = False,
    limit: int = Query(default=30, le=100),
) -> list[NotificationOut]:
    query = db.query(Notification)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return [NotificationOut.model_validate(row) for row in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, db: DbSession, user: CurrentUser) -> NotificationOut:
    row = db.get(Notification, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return NotificationOut.model_validate(row)


@router.post("/notifications/read-all")
def mark_all_read(db: DbSession, user: CurrentUser) -> dict:
    updated = (
        db.query(Notification).filter(Notification.is_read.is_(False)).update({"is_read": True})
    )
    db.commit()
    return {"updated": updated, "message": "All notifications marked as read"}


# ---------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(db: DbSession, admin: AdminUser) -> dict:
    rows = db.query(Setting).all()
    return {
        "settings": [
            {"key": row.key, "value": row.value, "description": row.description, "updated_at": row.updated_at}
            for row in rows
        ],
        "runtime": _runtime_info(db),
    }


@router.get("/settings/runtime")
def runtime_info(db: DbSession, user: CurrentUser) -> dict:
    return _runtime_info(db)


def _runtime_info(db) -> dict:
    def module_available(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    return {
        "product": app_settings.app_name,
        "version": app_settings.app_version,
        "environment": app_settings.environment,
        "database": "sqlite" if app_settings.is_sqlite else "postgresql",
        "database_url_masked": _mask_dsn(app_settings.database_url),
        "scheduler_enabled": app_settings.enable_scheduler,
        "monitoring_interval_seconds": app_settings.monitoring_interval_seconds,
        "local_collector": app_settings.enable_local_collector,
        "aws_mode": "simulated" if app_settings.aws_simulation_mode else "live",
        "aws_region": app_settings.aws_region,
        "ai_provider": app_settings.ai_provider,
        "ai_enabled": app_settings.ai_enabled,
        "log_retention_days": app_settings.log_retention_days,
        "cors_origins": app_settings.cors_origins,
        "warnings": app_settings.insecure_defaults,
        "database_size_bytes": _db_size(db),
        "tools": {
            "bandit": module_available("bandit") or bool(shutil.which("bandit")),
            "pip-audit": module_available("pip_audit") or bool(shutil.which("pip-audit")),
            "checkov": module_available("checkov") or bool(shutil.which("checkov")),
            "trivy": bool(shutil.which("trivy")),
            "docker": bool(shutil.which("docker")),
            "kubectl": bool(shutil.which("kubectl")),
            "terraform": bool(shutil.which("terraform")),
        },
    }


def _mask_dsn(dsn: str) -> str:
    if "@" not in dsn:
        return dsn
    prefix, rest = dsn.split("://", 1)
    credentials, host = rest.split("@", 1)
    user = credentials.split(":")[0]
    return f"{prefix}://{user}:***@{host}"


def _db_size(db) -> int | None:
    if not app_settings.is_sqlite:
        return None
    try:
        page_count = db.execute(text("PRAGMA page_count")).scalar() or 0
        page_size = db.execute(text("PRAGMA page_size")).scalar() or 0
        return int(page_count) * int(page_size)
    except Exception:  # pragma: no cover
        return None


@router.patch("/settings/log-retention")
def update_retention(
    db: DbSession,
    admin: AdminUser,
    days: int = Query(ge=1, le=365),
) -> dict:
    row = db.query(Setting).filter(Setting.key == "log_retention_days").first()
    if row:
        row.value = {"value": days}
    else:
        db.add(Setting(key="log_retention_days", value={"value": days}, description="Log retention window"))
    db.commit()
    record_audit(
        db,
        actor=admin.email,
        action="settings.log_retention_updated",
        entity_type="settings",
        entity_id="log_retention_days",
        detail={"days": days},
    )
    return {"retention_days": days, "message": "Retention updated. Runtime env value applies until restart."}


@router.post("/settings/cleanup")
def run_cleanup(db: DbSession, admin: AdminUser) -> dict:
    row = db.query(Setting).filter(Setting.key == "log_retention_days").first()
    days = app_settings.log_retention_days
    if row and isinstance(row.value, dict) and isinstance(row.value.get("value"), int):
        days = row.value["value"]
    deleted = retention_cleanup(db, days)
    record_audit(
        db,
        actor=admin.email,
        action="logs.retention_cleanup",
        entity_type="application_log",
        detail={"deleted": deleted, "days": days},
    )
    return {"deleted": deleted, "retention_days": days}


# --------------------------------------------------------------- dashboard
@router.get("/dashboard/overview")
def overview(db: DbSession, user: CurrentUser) -> dict:
    from app.schemas.domain import FindingOut, IncidentOut

    payload = dashboard_service.overview(db)
    payload["recent_incidents"] = [
        IncidentOut.model_validate(row).model_dump() for row in payload["recent_incidents"]
    ]
    payload["recent_findings"] = [
        FindingOut.model_validate(row).model_dump() for row in payload["recent_findings"]
    ]
    return payload


@router.get("/dashboard/trend")
def trend(db: DbSession, user: CurrentUser, hours: int = Query(default=12, ge=1, le=72)) -> list[dict]:
    return dashboard_service.fleet_trend(db, hours=hours)
