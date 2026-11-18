from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AdminUser, CurrentUser, DbSession, OperatorUser
from app.core.config import settings
from app.models import InfrastructureInstance, Metric, Threshold
from app.schemas.domain import AlertOut, MetricOut, ThresholdOut, ThresholdUpdate
from app.services import dashboard as dashboard_service
from app.services import monitoring
from app.services.audit import record_audit

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/summary")
def summary(db: DbSession, user: CurrentUser) -> dict:
    fleet = dashboard_service.fleet_counts(db)
    return {
        "instances": fleet,
        "utilisation": dashboard_service.utilisation(db),
        "thresholds": [ThresholdOut.model_validate(t).model_dump() for t in db.query(Threshold).all()],
        "interval_seconds": settings.monitoring_interval_seconds,
        "retention_hours": settings.monitoring_history_retention_hours,
        "scheduler_running": settings.enable_scheduler,
        "local_collector": settings.enable_local_collector,
        "metric_samples": db.query(Metric).count(),
        "data_sources": ["local (psutil)", "simulated (generator)"],
    }


@router.get("/alerts", response_model=list[AlertOut])
def alerts(
    db: DbSession, user: CurrentUser, limit: int = Query(default=20, le=100)
) -> list[AlertOut]:
    return [AlertOut(**alert) for alert in monitoring.current_alerts(db, limit=limit)]


@router.get("/metrics", response_model=list[MetricOut])
def fleet_metrics(
    db: DbSession,
    user: CurrentUser,
    instance_id: int | None = None,
    hours: int = Query(default=6, ge=1, le=168),
    limit: int = Query(default=1000, le=5000),
) -> list[MetricOut]:
    from datetime import timedelta

    from app.core.utils import utcnow

    query = db.query(Metric).filter(Metric.timestamp >= utcnow() - timedelta(hours=hours))
    if instance_id:
        query = query.filter(Metric.instance_id == instance_id)
    rows = query.order_by(Metric.timestamp.desc()).limit(limit).all()
    return [MetricOut.model_validate(row) for row in reversed(rows)]


@router.get("/thresholds", response_model=list[ThresholdOut])
def list_thresholds(db: DbSession, user: CurrentUser) -> list[ThresholdOut]:
    return [ThresholdOut.model_validate(row) for row in db.query(Threshold).order_by(Threshold.id)]


@router.patch("/thresholds/{metric}", response_model=ThresholdOut)
def update_threshold(
    metric: str,
    payload: ThresholdUpdate,
    db: DbSession,
    admin: AdminUser,
) -> ThresholdOut:
    row = db.query(Threshold).filter(Threshold.metric == metric).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No threshold configured for '{metric}'")
    if payload.warning is not None:
        row.warning = payload.warning
    if payload.critical is not None:
        row.critical = payload.critical
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if row.critical <= row.warning:
        raise HTTPException(status_code=422, detail="critical threshold must be greater than warning")
    db.commit()
    db.refresh(row)
    record_audit(
        db,
        actor=admin.email,
        action="threshold.updated",
        entity_type="threshold",
        entity_id=row.metric,
        detail={"warning": row.warning, "critical": row.critical, "enabled": row.enabled},
    )
    return ThresholdOut.model_validate(row)


@router.post("/collect")
def trigger_collection(db: DbSession, operator: OperatorUser) -> dict:
    result = monitoring.collect_all(db)
    record_audit(
        db,
        actor=operator.email,
        action="monitoring.collect",
        entity_type="monitoring",
        detail={
            "local_samples": result["local_samples"],
            "simulated_samples": result["simulated_samples"],
            "errors": result["errors"],
        },
    )
    return {
        **{k: v for k, v in result.items()},
        "message": "Collection cycle completed",
    }


@router.post("/spike")
def inject_spike(
    payload: dict,
    db: DbSession,
    operator: OperatorUser,
) -> dict:
    instance_id = payload.get("instance_id")
    metric = payload.get("metric", "cpu_percent")
    value = payload.get("value", 97)
    minutes = int(payload.get("minutes", 3))
    if metric not in {"cpu_percent", "memory_percent", "disk_percent"}:
        raise HTTPException(status_code=422, detail="metric must be cpu_percent, memory_percent or disk_percent")
    instance = db.get(InfrastructureInstance, instance_id) if instance_id else None
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    if instance.source != "simulated":
        raise HTTPException(status_code=400, detail="Spike injection only applies to simulated instances")
    result = monitoring.inject_spike(instance.id, metric, float(value), minutes)
    record_audit(
        db,
        actor=operator.email,
        action="monitoring.spike_injected",
        entity_type="instance",
        entity_id=instance.id,
        detail=result,
    )
    return {
        **result,
        "message": f"Simulated {metric} spike active for {minutes} minutes on {instance.name}",
    }


@router.get("/fleet")
def fleet(db: DbSession, user: CurrentUser) -> list[dict]:
    from app.schemas.domain import InstanceOut

    payload = []
    for row in monitoring.fleet_snapshot(db):
        instance = row["instance"]
        payload.append(
            {
                "instance": InstanceOut.model_validate(instance).model_dump(),
                "cpu_percent": row["cpu_percent"],
                "memory_percent": row["memory_percent"],
                "disk_percent": row["disk_percent"],
                "network_in_kbps": row["network_in_kbps"],
                "timestamp": row["timestamp"],
            }
        )
    return payload
