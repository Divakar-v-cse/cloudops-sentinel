"""Remediation engine.

Safety model
------------
* Actions can only be selected from ``ACTION_REGISTRY`` (an allowlist). Anything
  else is rejected before a record is created.
* No handler can touch real infrastructure. Handlers simulate the operation,
  run a health check before and after, and record exactly what they did.
* Any non-dry-run execution requires an approval by a different principal and
  is audited.
* Destructive operations (terminate instance, delete bucket, modify IAM or
  security groups, arbitrary shell) are not implemented at all - they are not
  in the registry, so they cannot be invoked.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.utils import utcnow
from app.models import (
    InfrastructureInstance,
    Metric,
    RemediationAction,
    RemediationRule,
)
from app.services.audit import record_audit
from app.services.notifications import notify


class RemediationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ActionSpec:
    name: str
    label: str
    description: str
    risk: str
    destructive: bool
    requires_approval: bool
    supports_dry_run: bool
    categories: tuple[str, ...]
    handler: Callable[[Session, InfrastructureInstance | None, str], tuple[bool, str]]


def _simulated_effect(instance: InfrastructureInstance | None, message: str) -> tuple[bool, str]:
    time.sleep(0.05)
    target = instance.name if instance else "unspecified target"
    return (
        True,
        f"[SIMULATED] {message}\nTarget: {target}\nNo cloud API was called and no workload was altered.",
    )


def _restart_service(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(
        instance,
        "Rolling restart requested for the application service. "
        "Orderly stop, health-gated start, readiness verified.",
    )


def _recycle_pool(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(instance, "Application connection pool recycled without dropping in-flight requests.")


def _clear_cache(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(instance, "Cache namespace flushed and warm-up started.")


def _rotate_logs(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(instance, "Log rotation forced and compressed archives pruned by retention policy.")


def _scale_replicas(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(
        instance, "Replica count increased by one within the configured maximum, then readiness verified."
    )


def _rollback_deployment(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    return _simulated_effect(
        instance,
        "Rollback to the previous healthy revision staged. In a real deployment this calls the CI/CD "
        "rollback job after approval.",
    )


def _run_health_check(db: Session, instance: InfrastructureInstance | None, target: str) -> tuple[bool, str]:
    if instance is None:
        return False, "Health check requires a target instance."
    latest = (
        db.query(Metric)
        .filter(Metric.instance_id == instance.id)
        .order_by(Metric.timestamp.desc())
        .first()
    )
    if latest is None:
        return False, f"No telemetry available for {instance.name}; cannot evaluate health."
    healthy = instance.health_status in {"healthy", "warning"}
    return (
        healthy,
        f"Health probe for {instance.name}: status={instance.health_status}, "
        f"cpu={latest.cpu_percent:.1f}%, memory={latest.memory_percent:.1f}%, disk={latest.disk_percent:.1f}%.",
    )


ACTION_REGISTRY: dict[str, ActionSpec] = {
    spec.name: spec
    for spec in [
        ActionSpec(
            name="restart_service",
            label="Restart application service",
            description="Orderly restart of the application process with a readiness gate.",
            risk="medium",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("availability", "application"),
            handler=_restart_service,
        ),
        ActionSpec(
            name="recycle_connection_pool",
            label="Recycle connection pool",
            description="Drain and rebuild the application's database connection pool.",
            risk="low",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("application", "database"),
            handler=_recycle_pool,
        ),
        ActionSpec(
            name="clear_cache",
            label="Clear application cache",
            description="Flush the cache namespace and warm it back up.",
            risk="low",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("performance",),
            handler=_clear_cache,
        ),
        ActionSpec(
            name="rotate_logs",
            label="Rotate logs",
            description="Force log rotation and prune archives beyond the retention policy.",
            risk="low",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("disk", "operations"),
            handler=_rotate_logs,
        ),
        ActionSpec(
            name="scale_out_replicas",
            label="Add one replica",
            description="Increase replica count by one, bounded by the configured maximum.",
            risk="medium",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("performance", "capacity"),
            handler=_scale_replicas,
        ),
        ActionSpec(
            name="rollback_deployment",
            label="Rollback last deployment",
            description="Redeploy the previous healthy revision through the CI/CD pipeline.",
            risk="high",
            destructive=False,
            requires_approval=True,
            supports_dry_run=True,
            categories=("deployment",),
            handler=_rollback_deployment,
        ),
        ActionSpec(
            name="run_health_check",
            label="Run health check",
            description="Read-only probe of the target's current health classification.",
            risk="low",
            destructive=False,
            requires_approval=False,
            supports_dry_run=True,
            categories=("diagnostics",),
            handler=_run_health_check,
        ),
    ]
}


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "label": spec.label,
            "description": spec.description,
            "risk": spec.risk,
            "destructive": spec.destructive,
            "requires_approval": spec.requires_approval,
            "supports_dry_run": spec.supports_dry_run,
            "categories": list(spec.categories),
        }
        for spec in ACTION_REGISTRY.values()
    ]


def _health_of(db: Session, instance_id: int | None) -> str | None:
    if instance_id is None:
        return None
    instance = db.get(InfrastructureInstance, instance_id)
    return instance.health_status if instance else None


def request_action(
    db: Session,
    *,
    action_name: str,
    actor: str,
    instance_id: int | None = None,
    incident_id: int | None = None,
    target: str | None = None,
    dry_run: bool = True,
    reason: str | None = None,
    rule_id: int | None = None,
) -> RemediationAction:
    spec = ACTION_REGISTRY.get(action_name)
    if spec is None:
        raise RemediationError(
            f"action '{action_name}' is not in the allowlisted action registry", status_code=422
        )
    instance = db.get(InfrastructureInstance, instance_id) if instance_id else None
    if instance_id and instance is None:
        raise RemediationError("target instance not found", status_code=404)
    resolved_target = target or (instance.name if instance else "fleet")
    if spec.destructive:
        raise RemediationError("destructive actions are disabled by policy", status_code=403)

    action = RemediationAction(
        rule_id=rule_id,
        incident_id=incident_id,
        instance_id=instance.id if instance else None,
        action_name=action_name,
        target=resolved_target,
        dry_run=dry_run,
        requested_by=actor,
        status="pending_approval" if not dry_run else "running",
        health_check_before=_health_of(db, instance_id),
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    record_audit(
        db,
        actor=actor,
        action="remediation.requested",
        entity_type="remediation_action",
        entity_id=action.id,
        detail={
            "action": action_name,
            "dry_run": dry_run,
            "target": resolved_target,
            "reason": reason,
            "risk": spec.risk,
        },
    )
    if dry_run:
        execute(db, action, actor=actor)
        db.refresh(action)
    else:
        notify(
            db,
            title=f"Approval required: {spec.label}",
            message=f"{actor} requested '{spec.label}' on {resolved_target}. Approve or reject in the Remediation Center.",
            severity="warning",
            category="remediation",
            entity_type="remediation_action",
            entity_id=action.id,
        )
    return action


def approve(db: Session, action: RemediationAction, *, actor: str, note: str | None = None) -> RemediationAction:
    if action.status != "pending_approval":
        raise RemediationError(f"action is {action.status}, not pending approval", status_code=409)
    if action.requested_by == actor:
        raise RemediationError(
            "the requester cannot approve their own production action (four-eyes principle)",
            status_code=403,
        )
    action.status = "approved"
    action.approved_by = actor
    action.approved_at = utcnow()
    db.commit()
    record_audit(
        db,
        actor=actor,
        action="remediation.approved",
        entity_type="remediation_action",
        entity_id=action.id,
        detail={"note": note, "requested_by": action.requested_by},
    )
    return action


def reject(db: Session, action: RemediationAction, *, actor: str, reason: str | None = None) -> RemediationAction:
    if action.status not in {"pending_approval", "approved"}:
        raise RemediationError(f"action is {action.status} and cannot be rejected", status_code=409)
    action.status = "rejected"
    action.approved_by = actor
    action.rejection_reason = reason or "Rejected without a stated reason"
    db.commit()
    record_audit(
        db,
        actor=actor,
        action="remediation.rejected",
        entity_type="remediation_action",
        entity_id=action.id,
        detail={"reason": action.rejection_reason},
    )
    return action


def execute(db: Session, action: RemediationAction, *, actor: str) -> RemediationAction:
    spec = ACTION_REGISTRY.get(action.action_name)
    if spec is None:
        action.status = "failed"
        action.error = "action is not in the allowlisted registry"
        db.commit()
        return action
    if not action.dry_run and action.status not in {"approved"}:
        raise RemediationError("production actions require approval before execution", status_code=403)

    instance = db.get(InfrastructureInstance, action.instance_id) if action.instance_id else None
    action.status = "running"
    db.commit()

    if action.dry_run:
        plan = (
            f"[DRY RUN] '{spec.label}' would run against {action.target}.\n"
            f"Risk: {spec.risk}. Approval required for real execution: {spec.requires_approval}.\n"
            "Validation performed: target exists, action is allowlisted, health baseline captured.\n"
            "No change was made."
        )
        action.output = plan
        action.status = "dry_run"
        action.executed_at = utcnow()
        db.commit()
        record_audit(
            db,
            actor=actor,
            action="remediation.dry_run",
            entity_type="remediation_action",
            entity_id=action.id,
            detail={"action": action.action_name, "target": action.target},
        )
        return action

    try:
        ok, output = spec.handler(db, instance, action.target)
    except Exception as exc:  # pragma: no cover - handler isolation
        action.status = "failed"
        action.error = str(exc)[:1000]
        action.executed_at = utcnow()
        db.commit()
        record_audit(
            db,
            actor=actor,
            action="remediation.failed",
            entity_type="remediation_action",
            entity_id=action.id,
            detail={"error": action.error},
        )
        return action

    action.output = output[:4000]
    action.executed_at = utcnow()
    action.health_check_after = _health_of(db, action.instance_id)
    action.status = "succeeded" if ok else "failed"
    if not ok:
        action.error = output[:1000]
    db.commit()

    record_audit(
        db,
        actor=actor,
        action=f"remediation.{action.status}",
        entity_type="remediation_action",
        entity_id=action.id,
        detail={
            "action": action.action_name,
            "target": action.target,
            "health_before": action.health_check_before,
            "health_after": action.health_check_after,
        },
    )
    notify(
        db,
        title=f"{spec.label} {action.status}",
        message=f"{spec.label} on {action.target} finished with status {action.status}.",
        severity="info" if action.status == "succeeded" else "warning",
        category="remediation",
        entity_type="remediation_action",
        entity_id=action.id,
    )
    return action


def evaluate_rules(db: Session) -> list[dict[str, Any]]:
    """Create pending actions when a rule's condition has held for its duration."""
    created: list[dict[str, Any]] = []
    rules = db.query(RemediationRule).filter(RemediationRule.enabled.is_(True)).all()
    if not rules:
        return created
    instances = db.query(InfrastructureInstance).filter(InfrastructureInstance.status == "running").all()
    for rule in rules:
        for instance in instances:
            samples = (
                db.query(Metric)
                .filter(Metric.instance_id == instance.id)
                .order_by(Metric.timestamp.desc())
                .limit(max(rule.duration_minutes, 1) * 4)
                .all()
            )
            if len(samples) < 2:
                continue
            values = [getattr(sample, rule.metric, None) for sample in samples]
            if any(value is None for value in values):
                continue
            matched = {
                ">": all(v > rule.threshold for v in values),
                ">=": all(v >= rule.threshold for v in values),
                "<": all(v < rule.threshold for v in values),
                "<=": all(v <= rule.threshold for v in values),
            }.get(rule.operator, False)
            if not matched:
                continue
            duplicate = (
                db.query(RemediationAction)
                .filter(
                    RemediationAction.rule_id == rule.id,
                    RemediationAction.instance_id == instance.id,
                    RemediationAction.status.in_(["pending_approval", "approved", "running"]),
                )
                .first()
            )
            if duplicate:
                continue
            action = request_action(
                db,
                action_name=rule.action_name,
                actor="remediation-engine",
                instance_id=instance.id,
                dry_run=rule.dry_run,
                reason=f"Rule '{rule.name}' matched {rule.metric} {rule.operator} {rule.threshold:g}",
                rule_id=rule.id,
            )
            created.append({"rule_id": rule.id, "instance_id": instance.id, "action_id": action.id})
    return created
