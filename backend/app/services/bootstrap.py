"""Idempotent bootstrap: schema, roles, demo fleet, telemetry history and seed records.

Every seeded record that represents synthetic infrastructure is tagged
``source='simulated'`` or ``simulated=True`` in its metadata so the UI can label it.
"""
from __future__ import annotations

import logging
import random
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.core.utils import utcnow
from app.models import (
    ApplicationLog,
    Base,
    CostRecord,
    Deployment,
    Incident,
    InfrastructureInstance,
    Metric,
    RemediationRule,
    Role,
    Setting,
    Threshold,
    User,
)
from app.services import cost as cost_service
from app.services import incidents as incident_service
from app.services import monitoring, security_scan
from app.services.notifications import notify
from app.services.remediation import request_action
from app.services.logs import fingerprint

logger = logging.getLogger(__name__)

ROLE_SPECS = [
    ("admin", "Full platform administration", {"*": ["*"]}),
    ("engineer", "Operate infrastructure, approve remediation", {"monitoring": ["read", "write"], "remediation": ["read", "request", "approve"]}),
    ("analyst", "Investigate incidents and analyse logs", {"monitoring": ["read"], "incidents": ["read", "write"], "logs": ["read", "write"]}),
    ("viewer", "Read-only access", {"*": ["read"]}),
]

SIMULATED_FLEET = [
    {
        "name": "prod-web-01",
        "external_id": "i-0a1f2b3c4d5e6f701",
        "instance_type": "t3.large",
        "environment": "production",
        "role": "web",
        "service": "web-frontend",
        "private_ip": "10.20.1.11",
        "public_ip": "54.201.18.44",
        "cpu_cores": 2,
        "memory_mb": 8192,
        "disk_gb": 80,
    },
    {
        "name": "prod-api-01",
        "external_id": "i-0b2c3d4e5f6071829",
        "instance_type": "m5.xlarge",
        "environment": "production",
        "role": "api",
        "service": "checkout-api",
        "private_ip": "10.20.2.21",
        "public_ip": "54.201.18.51",
        "cpu_cores": 4,
        "memory_mb": 16384,
        "disk_gb": 120,
    },
    {
        "name": "prod-api-02",
        "external_id": "i-0c3d4e5f60718293a",
        "instance_type": "m5.large",
        "environment": "production",
        "role": "api",
        "service": "payments-api",
        "private_ip": "10.20.2.22",
        "public_ip": "54.201.18.52",
        "cpu_cores": 2,
        "memory_mb": 8192,
        "disk_gb": 100,
    },
    {
        "name": "prod-worker-01",
        "external_id": "i-0d4e5f60718293a4b",
        "instance_type": "c5.xlarge",
        "environment": "production",
        "role": "worker",
        "service": "order-worker",
        "private_ip": "10.20.3.31",
        "public_ip": None,
        "cpu_cores": 4,
        "memory_mb": 8192,
        "disk_gb": 100,
    },
    {
        "name": "prod-db-01",
        "external_id": "i-0e5f60718293a4b5c",
        "instance_type": "r5.xlarge",
        "environment": "production",
        "role": "database",
        "service": "postgres-primary",
        "private_ip": "10.20.4.41",
        "public_ip": None,
        "cpu_cores": 4,
        "memory_mb": 32768,
        "disk_gb": 400,
    },
    {
        "name": "staging-api-01",
        "external_id": "i-0f60718293a4b5c6d",
        "instance_type": "t3.medium",
        "environment": "staging",
        "role": "api",
        "service": "checkout-api",
        "private_ip": "10.30.1.11",
        "public_ip": "54.201.18.61",
        "cpu_cores": 2,
        "memory_mb": 4096,
        "disk_gb": 60,
    },
    {
        "name": "dev-bastion",
        "external_id": "i-0102030405060708e",
        "instance_type": "t3.micro",
        "environment": "development",
        "role": "bastion",
        "service": "bastion",
        "private_ip": "10.40.0.5",
        "public_ip": "54.201.18.71",
        "cpu_cores": 2,
        "memory_mb": 1024,
        "disk_gb": 30,
    },
    {
        "name": "legacy-reporting",
        "external_id": "i-0203040506070809f",
        "instance_type": "m5.large",
        "environment": "production",
        "role": "worker",
        "service": "reporting",
        "private_ip": "10.20.5.51",
        "public_ip": None,
        "cpu_cores": 2,
        "memory_mb": 8192,
        "disk_gb": 100,
        "status": "stopped",
    },
]

LOG_TEMPLATES = [
    ("checkout-api", "ERROR", "Payment provider timeout after 3000ms for order {order} (trace {trace})"),
    ("checkout-api", "ERROR", "POST /v1/checkout returned 503 - upstream payments-api unavailable"),
    ("checkout-api", "WARN", "Retry attempt {n}/3 for order {order} after connection reset"),
    ("payments-api", "ERROR", "Connection refused connecting to redis-cache:6379"),
    ("payments-api", "ERROR", "psycopg2.OperationalError: remaining connection slots are reserved for non-replication superuser connections"),
    ("payments-api", "WARN", "Latency budget exceeded: GET /v1/payments p99=1240ms"),
    ("order-worker", "ERROR", "Container terminated with reason OOMKilled (memory limit 2Gi)"),
    ("order-worker", "ERROR", "Task order.reconcile failed: no space left on device"),
    ("order-worker", "INFO", "Processed batch of {n} orders in {ms}ms"),
    ("web-frontend", "ERROR", "502 Bad Gateway from upstream checkout-api"),
    ("web-frontend", "WARN", "Deprecation: legacy /cart/checkout endpoint called by client {n} times"),
    ("auth-service", "ERROR", "JWT validation failed: certificate expired for issuer auth.internal"),
    ("auth-service", "WARN", "Permission denied for service account deploy-bot on secretsmanager:GetSecretValue"),
    ("postgres-primary", "ERROR", "FATAL: too many connections for role app_rw"),
    ("postgres-primary", "WARN", "Checkpoint taking longer than usual: 42s"),
    ("deploy-agent", "ERROR", "Deployment checkout-api:v2.14.0 failed: ImagePullBackOff for registry.internal/checkout-api"),
    ("deploy-agent", "INFO", "Deployment payments-api:v2.13.4 completed in {ms}s"),
]


def _role_map(db: Session) -> dict[str, Role]:
    roles = {role.name: role for role in db.query(Role).all()}
    for name, description, permissions in ROLE_SPECS:
        if name not in roles:
            role = Role(name=name, description=description, permissions=permissions)
            db.add(role)
            roles[name] = role
    db.commit()
    return roles


def _users(db: Session, roles: dict[str, Role]) -> None:
    if db.query(func.count(User.id)).scalar():
        return
    db.add_all(
        [
            User(
                email=settings.default_admin_email,
                full_name="Platform Administrator",
                hashed_password=hash_password(settings.default_admin_password),
                role_id=roles["admin"].id,
                must_change_password=True,
            ),
            User(
                email="engineer@cloudops.local",
                full_name="SRE Engineer",
                hashed_password=hash_password(settings.default_admin_password),
                role_id=roles["engineer"].id,
                must_change_password=True,
            ),
            User(
                email="analyst@cloudops.local",
                full_name="Security Analyst",
                hashed_password=hash_password(settings.default_analyst_password),
                role_id=roles["analyst"].id,
                must_change_password=True,
            ),
        ]
    )
    db.commit()


def _instances(db: Session) -> list[InfrastructureInstance]:
    if db.query(func.count(InfrastructureInstance.id)).scalar():
        return db.query(InfrastructureInstance).all()
    pricing = cost_service.pricing_map(db)
    for spec in SIMULATED_FLEET:
        rate = pricing.get(spec["instance_type"])
        monthly = (
            round(rate.hourly_usd * settings.cost_hours_per_month + rate.ebs_gb_usd * spec["disk_gb"], 2)
            if rate
            else 0.0
        )
        tags = {
            "role": spec["role"],
            "service": spec["service"],
            "managed": "true",
            "data": "simulated",
        }
        db.add(
            InfrastructureInstance(
                name=spec["name"],
                external_id=spec["external_id"],
                provider="aws-simulated",
                source="simulated",
                instance_type=spec["instance_type"],
                region="us-east-1",
                environment=spec["environment"],
                status=spec.get("status", "running"),
                hostname=f"{spec['name']}.internal",
                os_name="Ubuntu 22.04 LTS",
                private_ip=spec["private_ip"],
                public_ip=spec["public_ip"],
                cpu_cores=spec["cpu_cores"],
                memory_mb=spec["memory_mb"],
                disk_gb=spec["disk_gb"],
                monthly_cost_usd=monthly,
                tags=tags,
                health_status="healthy" if spec.get("status") != "stopped" else "offline",
                last_seen_at=utcnow(),
            )
        )
    db.commit()
    return db.query(InfrastructureInstance).all()


def _backfill_metrics(db: Session, instances: list[InfrastructureInstance]) -> int:
    if db.query(func.count(Metric.id)).scalar():
        return 0
    now = utcnow()
    simulated = [i for i in instances if i.source == "simulated"]
    rows: list[Metric] = []
    random.seed(1337)
    for minutes_ago in range(360, -1, -5):
        ts = now - timedelta(minutes=minutes_ago)
        for instance in simulated:
            if instance.status == "stopped":
                continue
            sample = monitoring.simulate_snapshot(instance, ts)
            rows.append(
                Metric(
                    instance_id=instance.id,
                    timestamp=ts,
                    cpu_percent=sample.cpu_percent,
                    memory_percent=sample.memory_percent,
                    disk_percent=sample.disk_percent,
                    network_in_kbps=sample.network_in_kbps,
                    network_out_kbps=sample.network_out_kbps,
                    load_avg_1m=sample.load_avg_1m,
                    uptime_seconds=sample.uptime_seconds,
                    process_count=sample.process_count,
                    source="simulated",
                )
            )
    db.add_all(rows)
    db.commit()
    return len(rows)


def _cost_history(db: Session, instances: list[InfrastructureInstance]) -> None:
    if db.query(func.count(CostRecord.id)).scalar():
        return
    now = utcnow()
    periods: list[str] = []
    year, month = now.year, now.month
    for _ in range(4):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        periods.append(f"{year}-{month:02d}")
    periods.reverse()
    for period in periods:
        for instance in instances:
            if instance.monthly_cost_usd <= 0:
                continue
            variance = random.uniform(0.9, 1.08)
            db.add(
                CostRecord(
                    instance_id=instance.id,
                    service="EC2",
                    period=period,
                    estimated_cost_usd=round(instance.monthly_cost_usd * variance, 2),
                    source="simulated",
                    detail={"instance_type": instance.instance_type, "note": "simulated history"},
                )
            )
    db.commit()
    cost_service.record_monthly_snapshot(db)


def _logs(db: Session, instances: list[InfrastructureInstance]) -> None:
    if db.query(func.count(ApplicationLog.id)).scalar():
        return
    name_map = {instance.name: instance.id for instance in instances}
    service_instance = {
        "checkout-api": name_map.get("prod-api-01"),
        "payments-api": name_map.get("prod-api-02"),
        "order-worker": name_map.get("prod-worker-01"),
        "postgres-primary": name_map.get("prod-db-01"),
        "web-frontend": name_map.get("prod-web-01"),
        "auth-service": name_map.get("prod-api-02"),
        "deploy-agent": name_map.get("prod-worker-01"),
    }
    now = utcnow()
    random.seed(4242)
    rows: list[ApplicationLog] = []
    for index, (service, level, template) in enumerate(LOG_TEMPLATES * 7):
        message = template.format(
            order=random.randint(100000, 999999),
            trace=f"trc-{random.randint(100000, 999999)}",
            n=random.randint(2, 9),
            ms=random.randint(120, 4200),
        )
        severity = "critical" if "OOMKilled" in message or "FATAL" in message else (
            "error" if level == "ERROR" else "warning" if level == "WARN" else "info"
        )
        ts = now - timedelta(minutes=random.randint(3, 1400) + index)
        rows.append(
            ApplicationLog(
                service=service,
                level=level,
                severity=severity,
                message=message,
                timestamp=ts,
                fingerprint=fingerprint(service, message),
                instance_id=service_instance.get(service),
                trace_id=f"trc-{random.randint(100000, 999999)}",
                log_metadata={"seed": True, "data": "simulated"},
            )
        )
    db.add_all(rows)
    db.commit()


def _incidents(db: Session, instances: list[InfrastructureInstance]) -> None:
    if db.query(func.count(Incident.id)).scalar():
        return
    by_name = {instance.name: instance for instance in instances}
    incident_service.create_incident(
        db,
        title="Checkout API CPU saturation",
        description="CPU stayed above 92% for 12 minutes on prod-api-01; p99 latency rose to 2.4s.",
        severity="critical",
        service="checkout-api",
        instance_id=by_name["prod-api-01"].id if "prod-api-01" in by_name else None,
        detected_by="monitoring-engine",
        dedupe_key="threshold:prod-api-01:cpu_percent",
        actor="monitoring-engine",
    )
    b = incident_service.create_incident(
        db,
        title="Public S3 bucket exposed customer invoices",
        description="Security scan detected a bucket ACL granting AllUsers read access.",
        severity="high",
        service="storage",
        detected_by="security-scanner",
        actor="security-scanner",
    )
    incident_service.change_status(
        db, b, new_status="acknowledged", actor="analyst@cloudops.local",
        note="Acknowledged by security analyst; notifying the data platform owner.",
    )
    incident_service.change_status(
        db, b, new_status="investigating", actor="analyst@cloudops.local",
        note="Reviewing bucket policy history and CloudTrail data events.",
    )
    c = incident_service.create_incident(
        db,
        title="Failed deployment checkout-api v2.14.0",
        description="Rollout failed with ImagePullBackOff; previous revision v2.13.9 kept serving traffic.",
        severity="medium",
        service="checkout-api",
        detected_by="ci-pipeline",
        actor="ci-bot",
    )
    incident_service.change_status(
        db, c, new_status="acknowledged", actor="engineer@cloudops.local", note="On it."
    )
    incident_service.change_status(
        db,
        c,
        new_status="investigating",
        actor="engineer@cloudops.local",
        note="Registry credential secret had expired.",
    )
    incident_service.change_status(
        db,
        c,
        new_status="resolved",
        actor="engineer@cloudops.local",
        resolution_summary="Rotated the registry pull secret and re-ran the pipeline; v2.14.0 deployed successfully.",
        resolution_category="configuration",
    )
    incident_service.change_status(
        db, c, new_status="closed", actor="engineer@cloudops.local", note="Verified for 24h, closing."
    )
    d = incident_service.create_incident(
        db,
        title="Disk usage warning on prod-db-01",
        description="Data volume reached 82% after WAL growth.",
        severity="low",
        service="postgres-primary",
        instance_id=by_name["prod-db-01"].id if "prod-db-01" in by_name else None,
        detected_by="monitoring-engine",
        actor="monitoring-engine",
    )
    incident_service.change_status(
        db, d, new_status="acknowledged", actor="engineer@cloudops.local", note="Scheduled WAL archive cleanup."
    )
    incident_service.change_status(
        db, d, new_status="resolved", actor="engineer@cloudops.local",
        resolution_summary="Archived WAL segments to S3 and raised the volume alarm threshold review.",
        resolution_category="capacity",
    )


def _remediation(db: Session, instances: list[InfrastructureInstance]) -> None:
    if db.query(func.count(RemediationRule.id)).scalar():
        return
    rules = [
        RemediationRule(
            name="Restart on sustained CPU saturation",
            description="Restart the application service when CPU stays above 85% for 5 minutes.",
            metric="cpu_percent",
            operator=">",
            threshold=85.0,
            duration_minutes=5,
            action_name="restart_service",
            dry_run=True,
            requires_approval=True,
        ),
        RemediationRule(
            name="Rotate logs when disk fills",
            description="Force log rotation when disk usage stays above 90%.",
            metric="disk_percent",
            operator=">",
            threshold=90.0,
            duration_minutes=10,
            action_name="rotate_logs",
            dry_run=True,
            requires_approval=True,
        ),
        RemediationRule(
            name="Recycle pool on memory pressure",
            description="Recycle the connection pool when memory stays above 92%.",
            metric="memory_percent",
            operator=">",
            threshold=92.0,
            duration_minutes=5,
            action_name="recycle_connection_pool",
            dry_run=True,
            requires_approval=True,
        ),
    ]
    db.add_all(rules)
    db.commit()

    target = next((i for i in instances if i.name == "prod-api-01"), None)
    if target:
        request_action(
            db,
            action_name="run_health_check",
            actor="engineer@cloudops.local",
            instance_id=target.id,
            dry_run=True,
        )
        request_action(
            db,
            action_name="restart_service",
            actor="engineer@cloudops.local",
            instance_id=target.id,
            dry_run=False,
        )


def _deployments(db: Session) -> None:
    if db.query(func.count(Deployment.id)).scalar():
        return
    now = utcnow()
    rows = [
        ("checkout-api", "production", "v2.13.9", "success", "sentinel-release", 214, 360),
        ("checkout-api", "production", "v2.14.0", "failed", "sentinel-release", 96, 200),
        ("payments-api", "production", "v2.13.4", "success", "sentinel-release", 187, 150),
        ("web-frontend", "production", "v4.8.2", "success", "sentinel-ci", 143, 120),
        ("order-worker", "staging", "v1.9.0-rc3", "success", "sentinel-ci", 168, 90),
        ("checkout-api", "staging", "v2.14.0", "success", "sentinel-ci", 175, 70),
        ("payments-api", "staging", "v2.13.4", "failed", "sentinel-ci", 88, 48),
        ("web-frontend", "staging", "v4.8.3-rc1", "success", "sentinel-ci", 151, 26),
        ("infrastructure", "production", "tf-2026.11.1", "success", "sentinel-infrastructure", 312, 12),
    ]
    for service, environment, version, status, pipeline, duration, hours_ago in rows:
        started = now - timedelta(hours=hours_ago)
        db.add(
            Deployment(
                service=service,
                environment=environment,
                version=version,
                commit_sha=f"{random.getrandbits(40):010x}",
                status=status,
                pipeline=pipeline,
                stage="deploy" if status == "success" else "image-pull",
                triggered_by="ci-bot" if pipeline != "sentinel-infrastructure" else "terraform-bot",
                source="simulated",
                duration_seconds=duration,
                started_at=started,
                finished_at=started + timedelta(seconds=duration),
                detail={"data": "simulated", "note": "seeded deployment history"},
            )
        )
    db.commit()


def _findings(db: Session) -> None:
    from app.models import SecurityFinding

    if db.query(func.count(SecurityFinding.id)).scalar():
        return
    security_scan.run_scan(db, tools=["rules", "aws"], actor="bootstrap")


def _settings(db: Session) -> None:
    defaults = [
        ("monitoring_interval_seconds", {"value": settings.monitoring_interval_seconds}, "Telemetry collection interval"),
        ("log_retention_days", {"value": settings.log_retention_days}, "Log retention window"),
        ("cost_budget", {"budget_usd": settings.cost_budget_usd}, "Monthly cloud budget"),
        ("aws_simulation_mode", {"value": settings.aws_simulation_mode}, "AWS simulation toggle (read-only at runtime)"),
        ("ai_provider", {"value": settings.ai_provider}, "Configured log-analysis provider"),
    ]
    for key, value, description in defaults:
        if not db.query(Setting).filter(Setting.key == key).first():
            db.add(Setting(key=key, value=value, description=description))
    db.commit()


def _notifications(db: Session) -> None:
    from app.models import Notification

    if db.query(func.count(Notification.id)).scalar():
        return
    notify(
        db,
        title="CloudOps Sentinel initialised",
        message="Platform started in local mode. Simulated infrastructure is labelled throughout the UI.",
        severity="info",
        category="system",
    )
    notify(
        db,
        title="AWS simulation mode is active",
        message="No AWS account is connected. Enable AWS_SIMULATION_MODE=false with credentials to ingest real inventory.",
        severity="info",
        category="aws",
    )


def bootstrap(db: Session) -> dict[str, int]:
    stats: dict[str, int] = {}
    if db.query(func.count(Threshold.id)).scalar() == 0:
        monitoring.ensure_default_thresholds(db)
    cost_service.ensure_pricing(db)
    roles = _role_map(db)
    _users(db, roles)
    discovered = _instances(db)
    local = monitoring.register_local_instance(db)
    if local not in discovered:
        discovered.append(local)
    stats["metrics_backfilled"] = _backfill_metrics(db, discovered)
    _cost_history(db, discovered)
    _logs(db, discovered)
    _incidents(db, discovered)
    _remediation(db, discovered)
    _deployments(db)
    _findings(db)
    _settings(db)
    _notifications(db)
    monitoring.collect_all(db)
    logger.info("Bootstrap complete: %s", stats)
    return stats


def init_db() -> None:
    from app.db.session import engine

    Base.metadata.create_all(bind=engine)
