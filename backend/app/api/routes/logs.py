from __future__ import annotations

import math

from fastapi import APIRouter, Query
from sqlalchemy import func

from app.api.deps import AdminUser, CurrentUser, DbSession, OperatorUser
from app.core.config import settings
from app.models import ApplicationLog
from app.schemas.common import Paginated
from app.schemas.domain import LogAnalysis, LogGroup, LogIngestRequest, LogOut
from app.services import logs as log_service
from app.services.audit import record_audit

router = APIRouter(prefix="/logs", tags=["log intelligence"])


@router.post("")
def ingest(
    payload: LogIngestRequest,
    db: DbSession,
    operator: OperatorUser,
) -> dict:
    items = [item.model_dump() for item in payload.logs]
    if len(items) > settings.max_ingest_batch:
        items = items[: settings.max_ingest_batch]
    result = log_service.ingest(db, items)
    record_audit(
        db,
        actor=operator.email,
        action="logs.ingested",
        entity_type="application_log",
        detail={"count": result["ingested"], "services": result["services"]},
    )
    return {**result, "message": f"{result['ingested']} log records ingested"}


@router.get("", response_model=Paginated[LogOut])
def search(
    db: DbSession,
    user: CurrentUser,
    query: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    level: str | None = None,
    hours: int | None = Query(default=None, ge=1, le=720),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Paginated[LogOut]:
    rows, total = log_service.search(
        db,
        query=query,
        service=service,
        severity=severity,
        level=level,
        hours=hours,
        page=page,
        page_size=page_size,
    )
    return Paginated[LogOut](
        items=[LogOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/groups", response_model=list[LogGroup])
def groups(
    db: DbSession,
    user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=720),
    service: str | None = None,
    limit: int = Query(default=25, le=100),
) -> list[LogGroup]:
    return [LogGroup(**row) for row in log_service.groups(db, hours=hours, service=service, limit=limit)]


@router.get("/stats")
def stats(db: DbSession, user: CurrentUser, hours: int = Query(default=24, ge=1, le=720)) -> dict:
    return log_service.statistics(db, hours=hours)


@router.get("/services")
def services(db: DbSession, user: CurrentUser) -> list[dict]:
    rows = (
        db.query(ApplicationLog.service, func.count(ApplicationLog.id))
        .group_by(ApplicationLog.service)
        .order_by(func.count(ApplicationLog.id).desc())
        .all()
    )
    return [{"service": service, "count": count} for service, count in rows]


@router.post("/analyze", response_model=LogAnalysis)
def analyze(
    payload: dict,
    db: DbSession,
    user: CurrentUser,
) -> LogAnalysis:
    log_ids = payload.get("log_ids")
    if log_ids is not None and not isinstance(log_ids, list):
        log_ids = None
    result = log_service.analyse(
        db,
        log_ids=[int(i) for i in log_ids] if log_ids else None,
        fingerprint_value=payload.get("fingerprint"),
        service=payload.get("service"),
        hours=int(payload.get("hours", 24)),
    )
    record_audit(
        db,
        actor=user.email,
        action="logs.analyzed",
        entity_type="application_log",
        detail={
            "source": result["source"],
            "log_count": result.get("log_count", 0),
            "service": payload.get("service"),
        },
    )
    return LogAnalysis(**result)


@router.post("/retention/cleanup")
def cleanup(
    db: DbSession,
    admin: AdminUser,
    days: int | None = Query(default=None, ge=1, le=365),
) -> dict:
    deleted = log_service.retention_cleanup(db, days)
    record_audit(
        db,
        actor=admin.email,
        action="logs.retention_cleanup",
        entity_type="application_log",
        detail={"deleted": deleted, "retention_days": days or settings.log_retention_days},
    )
    return {
        "deleted": deleted,
        "retention_days": days or settings.log_retention_days,
        "message": f"Purged {deleted} log records beyond the retention window",
    }
