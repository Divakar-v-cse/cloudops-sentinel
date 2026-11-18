"""Dashboard aggregation built entirely from live database state."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import utcnow
from app.models import (
    ApplicationLog,
    Deployment,
    Incident,
    InfrastructureInstance,
    Metric,
    Notification,
    RemediationAction,
    SecurityFinding,
)
from app.services import cost as cost_service
from app.services import monitoring, security_scan
from app.services.incidents import OPEN_STATUSES

SEVERITY_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 1}


def fleet_counts(db: Session) -> dict[str, Any]:
    rows = db.query(InfrastructureInstance).all()
    by_health = {"healthy": 0, "warning": 0, "critical": 0, "offline": 0, "unknown": 0}
    by_source = {"local": 0, "simulated": 0, "aws": 0}
    for instance in rows:
        health = instance.health_status or "unknown"
        by_health[health] = by_health.get(health, 0) + 1
        by_source[instance.source] = by_source.get(instance.source, 0) + 1
    return {
        "total": len(rows),
        "by_health": by_health,
        "by_source": by_source,
        "running": sum(1 for row in rows if row.status == "running"),
    }


def utilisation(db: Session) -> dict[str, float | None]:
    subquery = (
        db.query(Metric.instance_id, func.max(Metric.timestamp).label("ts"))
        .group_by(Metric.instance_id)
        .subquery()
    )
    rows = (
        db.query(func.avg(Metric.cpu_percent), func.avg(Metric.memory_percent), func.avg(Metric.disk_percent))
        .join(subquery, subquery.c.ts == Metric.timestamp)
        .filter(Metric.timestamp == subquery.c.ts)
        .one()
    )
    return {
        "cpu": round(float(rows[0]), 1) if rows[0] is not None else None,
        "memory": round(float(rows[1]), 1) if rows[1] is not None else None,
        "disk": round(float(rows[2]), 1) if rows[2] is not None else None,
    }


def fleet_trend(db: Session, hours: int = 12) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(hours=hours)
    bucket = (
        func.strftime("%Y-%m-%d %H:00", Metric.timestamp)
        if settings.is_sqlite
        else func.date_trunc("hour", Metric.timestamp)
    )
    rows = (
        db.query(
            bucket.label("bucket"),
            func.avg(Metric.cpu_percent),
            func.avg(Metric.memory_percent),
            func.avg(Metric.disk_percent),
        )
        .filter(Metric.timestamp >= since)
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )
    return [
        {
            "bucket": str(row[0]),
            "cpu": round(float(row[1] or 0), 1),
            "memory": round(float(row[2] or 0), 1),
            "disk": round(float(row[3] or 0), 1),
        }
        for row in rows
    ]


def overview(db: Session) -> dict[str, Any]:
    now = utcnow()
    fleet = fleet_counts(db)
    usage = utilisation(db)
    open_incidents = db.query(Incident).filter(Incident.status.in_(OPEN_STATUSES)).all()
    critical_open = sum(1 for incident in open_incidents if incident.severity == "critical")
    high_open = sum(1 for incident in open_incidents if incident.severity == "high")

    findings = db.query(SecurityFinding).filter(SecurityFinding.status == "open").all()
    security_critical = sum(1 for finding in findings if finding.severity == "critical")
    security_high = sum(1 for finding in findings if finding.severity == "high")
    risk_score = min(
        100, sum(SEVERITY_WEIGHT.get(finding.severity, 1) for finding in findings)
    )

    costs = cost_service.summary(db)
    deploy_summary = db.query(Deployment).order_by(Deployment.started_at.desc()).first()
    last_24h = now - timedelta(hours=24)
    error_logs = (
        db.query(func.count(ApplicationLog.id))
        .filter(ApplicationLog.timestamp >= last_24h, ApplicationLog.severity.in_(["error", "critical"]))
        .scalar()
        or 0
    )
    pending_actions = (
        db.query(func.count(RemediationAction.id))
        .filter(RemediationAction.status == "pending_approval")
        .scalar()
        or 0
    )
    alerts = monitoring.current_alerts(db, limit=8)

    recent_incidents = (
        db.query(Incident).order_by(Incident.created_at.desc()).limit(5).all()
    )
    recent_findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.status == "open")
        .order_by(SecurityFinding.last_seen_at.desc())
        .limit(5)
        .all()
    )
    unread = db.query(func.count(Notification.id)).filter(Notification.is_read.is_(False)).scalar() or 0

    return {
        "generated_at": now,
        "mode": {
            "aws": "simulated" if not _aws_connected(db) else "connected",
            "data_sources": fleet["by_source"],
            "scheduler": settings.enable_scheduler,
        },
        "instances": fleet,
        "utilisation": usage,
        "incidents": {
            "open": len(open_incidents),
            "critical": critical_open,
            "high": high_open,
            "total": db.query(func.count(Incident.id)).scalar() or 0,
        },
        "security": {
            "open_findings": len(findings),
            "critical": security_critical,
            "high": security_high,
            "risk_score": risk_score,
            "risk_level": security_scan.severity_summary(db)["risk_level"],
        },
        "cost": {
            "estimated_monthly_usd": costs["estimated_monthly_usd"],
            "budget_usd": costs["budget_usd"],
            "budget_used_percent": costs["budget_used_percent"],
            "potential_savings_usd": costs["potential_savings_usd"],
            "currency": costs["currency"],
            "source": costs["source"],
        },
        "deployments": {
            "last_status": deploy_summary.status if deploy_summary else "unknown",
            "last_service": deploy_summary.service if deploy_summary else None,
            "last_version": deploy_summary.version if deploy_summary else None,
            "last_at": deploy_summary.started_at if deploy_summary else None,
            "success_rate": _deployment_success_rate(db),
            "source": deploy_summary.source if deploy_summary else None,
        },
        "logs": {"errors_24h": error_logs},
        "remediation": {"pending_approvals": pending_actions},
        "notifications": {"unread": unread},
        "alerts": alerts,
        "trend": fleet_trend(db),
        "recent_incidents": recent_incidents,
        "recent_findings": recent_findings,
    }


def _deployment_success_rate(db: Session) -> float:
    total = db.query(func.count(Deployment.id)).scalar() or 0
    if not total:
        return 0.0
    success = db.query(func.count(Deployment.id)).filter(Deployment.status == "success").scalar() or 0
    return round(success / total * 100, 1)


def _aws_connected(db: Session) -> bool:
    from app.services import aws as aws_service

    return bool(aws_service.connection_status().get("connected"))
