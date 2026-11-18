"""Infrastructure monitoring engine.

Two clearly separated producers:

* ``collect_local_snapshot`` - real measurements of the host this process runs on
  (psutil). Data is stored with ``source='local'``.
* ``simulate_snapshot`` - deterministic, seeded synthetic telemetry for the
  built-in simulated fleet. Data is stored with ``source='simulated'`` and is
  never presented as a real machine.

The engine also classifies health, raises threshold alerts (rate limited) and
opens incidents for sustained critical conditions.
"""
from __future__ import annotations

import math
import os
import random
import platform
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import psutil
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import utcnow
from app.models import InfrastructureInstance, Metric, Threshold
from app.services import incidents as incident_service
from app.services.notifications import notify

# --------------------------------------------------------------- state
_NET_STATE: dict[int, tuple[float, int, int]] = {}
_SPIKES: dict[int, dict[str, Any]] = {}
_LOCK = threading.Lock()
_LAST_ALERT: dict[tuple[int, str, str], datetime] = {}
_ALERT_COOLDOWN = timedelta(minutes=10)

ROLE_PROFILES: dict[str, dict[str, float]] = {
    "web": {"cpu": 34, "mem": 58, "disk": 46, "net": 900},
    "api": {"cpu": 46, "mem": 64, "disk": 52, "net": 1400},
    "worker": {"cpu": 58, "mem": 71, "disk": 61, "net": 600},
    "database": {"cpu": 41, "mem": 78, "disk": 74, "net": 1100},
    "cache": {"cpu": 18, "mem": 52, "disk": 30, "net": 2200},
    "bastion": {"cpu": 7, "mem": 26, "disk": 22, "net": 90},
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ------------------------------------------------------------ thresholds
def get_thresholds(db: Session) -> dict[str, Threshold]:
    rows = db.query(Threshold).filter(Threshold.enabled.is_(True)).all()
    return {row.metric: row for row in rows}


def ensure_default_thresholds(db: Session) -> None:
    defaults = [
        ("cpu_percent", "CPU utilization", "%", settings.cpu_warning, settings.cpu_critical),
        ("memory_percent", "Memory utilization", "%", settings.memory_warning, settings.memory_critical),
        ("disk_percent", "Disk utilization", "%", settings.disk_warning, settings.disk_critical),
        (
            "network_in_kbps",
            "Network ingress",
            "kbps",
            settings.network_warning_kbps,
            settings.network_critical_kbps,
        ),
    ]
    existing = {row.metric for row in db.query(Threshold).all()}
    for metric, label, unit, warn, crit in defaults:
        if metric not in existing:
            db.add(
                Threshold(
                    metric=metric,
                    display_name=label,
                    unit=unit,
                    warning=warn,
                    critical=crit,
                    enabled=True,
                )
            )
    db.commit()


def classify(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "healthy"


def classify_health(
    cpu: float, memory: float, disk: float, thresholds: dict[str, Threshold]
) -> str:
    levels = []
    for metric, value in (("cpu_percent", cpu), ("memory_percent", memory), ("disk_percent", disk)):
        th = thresholds.get(metric)
        if th:
            levels.append(classify(value, th.warning, th.critical))
    if "critical" in levels:
        return "critical"
    if "warning" in levels:
        return "warning"
    return "healthy"


# ------------------------------------------------------------- local host
def _local_instance(db: Session) -> InfrastructureInstance | None:
    return (
        db.query(InfrastructureInstance)
        .filter(InfrastructureInstance.source == "local")
        .order_by(InfrastructureInstance.id)
        .first()
    )


def collect_local_snapshot(db: Session) -> Metric | None:
    """Measure this host with psutil and persist the sample."""
    instance = _local_instance(db)
    if instance is None:
        return None

    now = utcnow()
    cpu = float(psutil.cpu_percent(interval=None))
    mem = psutil.virtual_memory()
    disk_path = os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(disk_path)
        disk_percent = float(disk.percent)
    except OSError:
        disk_percent = 0.0

    counters = psutil.net_io_counters()
    prev = _NET_STATE.get(instance.id)
    if prev:
        elapsed = max(now.timestamp() - prev[0], 0.001)
        in_kbps = max((counters.bytes_recv - prev[1]) * 8 / 1024 / elapsed, 0.0)
        out_kbps = max((counters.bytes_sent - prev[2]) * 8 / 1024 / elapsed, 0.0)
    else:
        in_kbps = out_kbps = 0.0
    _NET_STATE[instance.id] = (now.timestamp(), counters.bytes_recv, counters.bytes_sent)

    try:
        load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    except OSError:
        load1 = 0.0

    metric = Metric(
        instance_id=instance.id,
        timestamp=now,
        cpu_percent=round(cpu, 2),
        memory_percent=round(float(mem.percent), 2),
        disk_percent=round(disk_percent, 2),
        network_in_kbps=round(in_kbps, 2),
        network_out_kbps=round(out_kbps, 2),
        load_avg_1m=round(float(load1), 2),
        uptime_seconds=int(time.time() - psutil.boot_time()),
        process_count=len(psutil.pids()),
        source="local",
    )
    db.add(metric)
    instance.last_seen_at = now
    instance.health_status = classify_health(
        cpu, metric.memory_percent, disk_percent, get_thresholds(db)
    )
    db.commit()
    db.refresh(metric)
    evaluate_thresholds(db, instance, metric)
    return metric


def register_local_instance(db: Session) -> InfrastructureInstance:
    """Create/refresh the inventory row describing the machine running Sentinel."""
    instance = _local_instance(db)
    hostname = socket.gethostname()
    mem_total_mb = int(psutil.virtual_memory().total / 1024 / 1024)
    try:
        disk_gb = int(psutil.disk_usage(os.path.abspath(os.sep)).total / 1024**3)
    except OSError:
        disk_gb = 0
    os_name = f"{platform.system()} {platform.release()}"
    values = {
        "name": f"local-{hostname}",
        "hostname": hostname,
        "os_name": os_name,
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "memory_mb": mem_total_mb,
        "disk_gb": disk_gb,
        "instance_type": "local-host",
        "region": "on-prem",
        "environment": "local",
        "status": "running",
        "health_status": "healthy",
        "monthly_cost_usd": 0.0,
        "tags": {"managed": "true", "note": "measured by psutil on this machine"},
    }
    if instance is None:
        instance = InfrastructureInstance(
            provider="local", source="local", private_ip="127.0.0.1", **values
        )
        db.add(instance)
    else:
        for key, value in values.items():
            setattr(instance, key, value)
    db.commit()
    db.refresh(instance)
    return instance


# --------------------------------------------------------------- simulator
def inject_spike(instance_id: int, metric: str, value: float, minutes: int = 2) -> dict[str, Any]:
    with _LOCK:
        _SPIKES[instance_id] = {
            "metric": metric,
            "value": value,
            "until": utcnow() + timedelta(minutes=minutes),
        }
    return {"instance_id": instance_id, "metric": metric, "value": value, "minutes": minutes}


def active_spikes() -> dict[int, dict[str, Any]]:
    now = utcnow()
    with _LOCK:
        expired = [key for key, val in _SPIKES.items() if val["until"] < now]
        for key in expired:
            _SPIKES.pop(key, None)
        return dict(_SPIKES)


def simulate_snapshot(instance: InfrastructureInstance, now: datetime | None = None) -> Metric:
    now = now or utcnow()
    role = str((instance.tags or {}).get("role", "web"))
    profile = ROLE_PROFILES.get(role, ROLE_PROFILES["web"])
    # deterministic per-instance phase so charts look distinct but stable
    phase = (instance.id * 37) % 360 / 57.2958
    hours = now.hour + now.minute / 60
    daily = math.sin((hours / 24) * 2 * math.pi - 1.2 + phase) * 18
    noise = random.uniform(-4.5, 4.5)

    cpu = _clamp(profile["cpu"] + daily * 0.55 + noise)
    memory = _clamp(profile["mem"] + daily * 0.35 + random.uniform(-2.5, 2.5))
    disk = _clamp(profile["disk"] + (now.day % 7) * 0.6 + random.uniform(-0.4, 0.4))
    net_in = max(profile["net"] * (0.55 + random.random()) + daily * 12, 5.0)

    # occasional organic spike
    if random.random() < 0.035:
        cpu = _clamp(cpu + random.uniform(28, 55))

    spikes = active_spikes()
    spike = spikes.get(instance.id)
    if spike:
        if spike["metric"] == "cpu_percent":
            cpu = _clamp(float(spike["value"]))
        elif spike["metric"] == "memory_percent":
            memory = _clamp(float(spike["value"]))
        elif spike["metric"] == "disk_percent":
            disk = _clamp(float(spike["value"]))

    if instance.status == "stopped":
        cpu = memory = net_in = 0.0

    metric = Metric(
        instance_id=instance.id,
        timestamp=now,
        cpu_percent=round(cpu, 2),
        memory_percent=round(memory, 2),
        disk_percent=round(disk, 2),
        network_in_kbps=round(net_in, 2),
        network_out_kbps=round(net_in * random.uniform(0.35, 0.8), 2),
        load_avg_1m=round(cpu / 100 * max(instance.cpu_cores, 1), 2),
        uptime_seconds=(
            0 if instance.status == "stopped" else int(random.uniform(3600, 86400 * 40))
        ),
        process_count=0 if instance.status == "stopped" else random.randint(48, 340),
        source="simulated",
    )
    instance.last_seen_at = now
    return metric


def simulate_all(db: Session) -> int:
    instances = (
        db.query(InfrastructureInstance)
        .filter(InfrastructureInstance.source == "simulated")
        .all()
    )
    thresholds = get_thresholds(db)
    now = utcnow()
    created: list[tuple[InfrastructureInstance, Metric]] = []
    for instance in instances:
        metric = simulate_snapshot(instance, now)
        metric_values = (metric.cpu_percent, metric.memory_percent, metric.disk_percent)
        instance.health_status = (
            "offline"
            if instance.status == "stopped"
            else classify_health(*metric_values, thresholds)
        )
        db.add(metric)
        created.append((instance, metric))
    db.commit()
    for instance, metric in created:
        evaluate_thresholds(db, instance, metric)
    return len(created)


# ------------------------------------------------------------------ alerts
def evaluate_thresholds(
    db: Session, instance: InfrastructureInstance, metric: Metric
) -> list[dict[str, Any]]:
    if instance.status == "stopped":
        return []
    thresholds = get_thresholds(db)
    alerts: list[dict[str, Any]] = []
    for metric_name, value in (
        ("cpu_percent", metric.cpu_percent),
        ("memory_percent", metric.memory_percent),
        ("disk_percent", metric.disk_percent),
        ("network_in_kbps", metric.network_in_kbps),
    ):
        th = thresholds.get(metric_name)
        if not th:
            continue
        level = classify(value, th.warning, th.critical)
        if level == "healthy":
            continue
        key = (instance.id, metric_name, level)
        last = _LAST_ALERT.get(key)
        if last and utcnow() - last < _ALERT_COOLDOWN:
            continue
        _LAST_ALERT[key] = utcnow()
        unit = th.unit
        message = (
            f"{instance.name}: {th.display_name} at {value:.1f}{unit} "
            f"({level} threshold {th.critical if level == 'critical' else th.warning:.0f}{unit})"
        )
        notify(
            db,
            title=f"{level.upper()}: {instance.name}",
            message=message,
            severity="critical" if level == "critical" else "warning",
            category="monitoring",
            entity_type="instance",
            entity_id=instance.id,
        )
        alerts.append(
            {
                "instance_id": instance.id,
                "instance_name": instance.name,
                "metric": metric_name,
                "value": value,
                "threshold": th.critical if level == "critical" else th.warning,
                "level": level,
                "message": message,
                "timestamp": metric.timestamp,
                "source": instance.source,
            }
        )
        if level == "critical":
            incident_service.auto_open_incident(
                db,
                title=f"{th.display_name} critical on {instance.name}",
                description=message,
                severity="critical" if value >= th.critical * 1.03 else "high",
                service=(instance.tags or {}).get("service", instance.name),
                instance_id=instance.id,
                dedupe_key=f"threshold:{instance.id}:{metric_name}",
                detected_by="monitoring-engine",
            )
    return alerts


def current_alerts(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Derive live alerts from the newest metric of every instance."""
    thresholds = get_thresholds(db)
    instances = db.query(InfrastructureInstance).all()
    alerts: list[dict[str, Any]] = []
    for instance in instances:
        latest = (
            db.query(Metric)
            .filter(Metric.instance_id == instance.id)
            .order_by(Metric.timestamp.desc())
            .first()
        )
        if not latest:
            continue
        for metric_name, value in (
            ("cpu_percent", latest.cpu_percent),
            ("memory_percent", latest.memory_percent),
            ("disk_percent", latest.disk_percent),
            ("network_in_kbps", latest.network_in_kbps),
        ):
            th = thresholds.get(metric_name)
            if not th:
                continue
            level = classify(value, th.warning, th.critical)
            if level == "healthy":
                continue
            alerts.append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "metric": metric_name,
                    "value": value,
                    "threshold": th.critical if level == "critical" else th.warning,
                    "level": level,
                    "message": f"{th.display_name} {value:.1f}{th.unit} on {instance.name}",
                    "timestamp": latest.timestamp,
                    "source": instance.source,
                }
            )
    alerts.sort(key=lambda item: (item["level"] != "critical", -item["value"]))
    return alerts[:limit]


# ------------------------------------------------------------------ orchestration
def collect_all(db: Session) -> dict[str, Any]:
    started = utcnow()
    local_samples = 0
    simulated_samples = 0
    errors: list[str] = []
    if settings.enable_local_collector:
        try:
            if collect_local_snapshot(db):
                local_samples = 1
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"local collector: {exc}")
    try:
        simulated_samples = simulate_all(db)
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"simulator: {exc}")
    prune_history(db)
    return {
        "collected_at": started,
        "local_samples": local_samples,
        "simulated_samples": simulated_samples,
        "errors": errors,
    }


def prune_history(db: Session) -> int:
    cutoff = utcnow() - timedelta(hours=settings.monitoring_history_retention_hours)
    deleted = db.query(Metric).filter(Metric.timestamp < cutoff).delete()
    db.commit()
    return deleted


def fleet_snapshot(db: Session) -> list[dict[str, Any]]:
    """Latest metric per instance, used by inventory + dashboard pages."""
    subquery = (
        db.query(Metric.instance_id, func.max(Metric.timestamp).label("ts"))
        .group_by(Metric.instance_id)
        .subquery()
    )
    rows = (
        db.query(InfrastructureInstance, Metric)
        .outerjoin(subquery, subquery.c.instance_id == InfrastructureInstance.id)
        .outerjoin(
            Metric,
            (Metric.instance_id == InfrastructureInstance.id) & (Metric.timestamp == subquery.c.ts),
        )
        .order_by(InfrastructureInstance.name)
        .all()
    )
    payload: list[dict[str, Any]] = []
    for instance, metric in rows:
        payload.append(
            {
                "instance": instance,
                "metric": metric,
                "cpu_percent": metric.cpu_percent if metric else None,
                "memory_percent": metric.memory_percent if metric else None,
                "disk_percent": metric.disk_percent if metric else None,
                "network_in_kbps": metric.network_in_kbps if metric else None,
                "timestamp": metric.timestamp if metric else None,
            }
        )
    return payload
