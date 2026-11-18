"""Incident lifecycle: DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> RESOLVED -> CLOSED."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.utils import utcnow
from app.models import Incident, IncidentNote
from app.services.audit import record_audit
from app.services.notifications import notify

STATUSES = ["detected", "acknowledged", "investigating", "resolved", "closed"]
SEVERITIES = ["critical", "high", "medium", "low"]
OPEN_STATUSES = ["detected", "acknowledged", "investigating"]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "detected": {"acknowledged", "investigating", "resolved"},
    "acknowledged": {"investigating", "resolved"},
    "investigating": {"resolved"},
    "resolved": {"closed", "investigating"},
    "closed": {"detected"},
}

TRANSITION_LABEL = {
    "acknowledged": "Acknowledged",
    "investigating": "Investigation started",
    "resolved": "Resolved",
    "closed": "Closed",
    "detected": "Reopened",
}

SEVERITY_WEIGHT = {"critical": 40, "high": 25, "medium": 12, "low": 5}


class IncidentError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def next_incident_number(db: Session) -> str:
    year = utcnow().year
    prefix = f"INC-{year}-"
    count = db.query(func.count(Incident.id)).filter(Incident.incident_number.like(f"{prefix}%")).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def create_incident(
    db: Session,
    *,
    title: str,
    description: str = "",
    severity: str = "medium",
    service: str | None = None,
    instance_id: int | None = None,
    assigned_to: str | None = None,
    detected_by: str = "manual",
    dedupe_key: str | None = None,
    actor: str = "system",
    status: str = "detected",
) -> Incident:
    if severity not in SEVERITIES:
        raise IncidentError(f"invalid severity '{severity}'")
    if dedupe_key:
        existing = (
            db.query(Incident)
            .filter(Incident.dedupe_key == dedupe_key, Incident.status.in_(OPEN_STATUSES))
            .order_by(Incident.id.desc())
            .first()
        )
        if existing:
            existing.updated_at = utcnow()
            db.commit()
            return existing

    incident = Incident(
        incident_number=next_incident_number(db),
        title=title[:240],
        description=description,
        severity=severity,
        status=status,
        service=service,
        instance_id=instance_id,
        assigned_to=assigned_to,
        detected_by=detected_by,
        dedupe_key=dedupe_key,
        acknowledged_at=utcnow() if status != "detected" else None,
    )
    db.add(incident)
    db.flush()
    db.add(
        IncidentNote(
            incident_id=incident.id,
            author="system" if detected_by != "manual" else actor,
            note=f"Incident opened by {detected_by}.",
            note_type="timeline",
            status_change="detected",
        )
    )
    db.commit()
    db.refresh(incident)
    notify(
        db,
        title=f"New {severity} incident {incident.incident_number}",
        message=title,
        severity="critical" if severity == "critical" else "warning",
        category="incident",
        entity_type="incident",
        entity_id=incident.id,
    )
    record_audit(
        db,
        actor=actor,
        action="incident.created",
        entity_type="incident",
        entity_id=incident.id,
        detail={"severity": severity, "detected_by": detected_by},
    )
    return incident


def auto_open_incident(
    db: Session,
    *,
    title: str,
    description: str,
    severity: str,
    service: str | None,
    instance_id: int | None,
    dedupe_key: str,
    detected_by: str = "monitoring-engine",
) -> Incident:
    return create_incident(
        db,
        title=title,
        description=description,
        severity=severity,
        service=service,
        instance_id=instance_id,
        detected_by=detected_by,
        dedupe_key=dedupe_key,
        actor="monitoring-engine",
    )


def change_status(
    db: Session,
    incident: Incident,
    *,
    new_status: str,
    actor: str,
    note: str | None = None,
    resolution_summary: str | None = None,
    resolution_category: str | None = None,
) -> Incident:
    if new_status not in STATUSES:
        raise IncidentError(f"unknown status '{new_status}'")
    if new_status == incident.status:
        raise IncidentError(f"incident is already {new_status}")
    if new_status not in ALLOWED_TRANSITIONS.get(incident.status, set()):
        raise IncidentError(
            f"illegal transition {incident.status} -> {new_status}; "
            f"allowed: {', '.join(sorted(ALLOWED_TRANSITIONS.get(incident.status, set())))}",
            status_code=409,
        )
    if new_status == "resolved" and not (resolution_summary or note):
        raise IncidentError("a resolution summary is required to resolve an incident")

    now = utcnow()
    incident.status = new_status
    if new_status == "acknowledged":
        incident.acknowledged_at = incident.acknowledged_at or now
    elif new_status == "resolved":
        incident.resolved_at = now
        incident.resolution_summary = (resolution_summary or note or "")[:4000]
        incident.resolution_category = resolution_category
    elif new_status == "closed":
        incident.closed_at = now
    elif new_status == "detected":
        incident.acknowledged_at = None
        incident.resolved_at = None
        incident.closed_at = None
        incident.resolution_summary = None
    incident.updated_at = now

    message = note or f"Status changed to {new_status}"
    db.add(
        IncidentNote(
            incident_id=incident.id,
            author=actor,
            note=message,
            note_type="timeline",
            status_change=new_status,
        )
    )
    db.commit()
    db.refresh(incident)
    record_audit(
        db,
        actor=actor,
        action=f"incident.{new_status}",
        entity_type="incident",
        entity_id=incident.id,
        detail={"from": new_status, "note": note},
    )
    return incident


def add_note(
    db: Session,
    incident: Incident,
    *,
    author: str,
    note: str,
    note_type: str = "investigation",
) -> IncidentNote:
    entry = IncidentNote(
        incident_id=incident.id, author=author, note=note, note_type=note_type
    )
    db.add(entry)
    incident.updated_at = utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def statistics(db: Session) -> dict[str, Any]:
    rows = db.query(Incident).all()
    now = utcnow()
    week_ago = now - timedelta(days=7)
    by_status = {status: 0 for status in STATUSES}
    by_severity = {sev: 0 for sev in SEVERITIES}
    for incident in rows:
        by_status[incident.status] = by_status.get(incident.status, 0) + 1
        by_severity[incident.severity] = by_severity.get(incident.severity, 0) + 1

    resolved = [i for i in rows if i.resolved_at and i.acknowledged_at]
    mttr = (
        sum((i.resolved_at - i.acknowledged_at).total_seconds() for i in resolved) / len(resolved) / 60
        if resolved
        else None
    )
    ack = [i for i in rows if i.acknowledged_at]
    mtta = (
        sum((i.acknowledged_at - i.created_at).total_seconds() for i in ack) / len(ack) / 60
        if ack
        else None
    )
    open_incidents = [i for i in rows if i.status in OPEN_STATUSES]
    risk_score = min(
        100,
        sum(SEVERITY_WEIGHT.get(i.severity, 5) for i in open_incidents),
    )
    return {
        "total": len(rows),
        "open": len(open_incidents),
        "by_status": by_status,
        "by_severity": by_severity,
        "critical_open": sum(1 for i in open_incidents if i.severity == "critical"),
        "mttr_minutes": round(mttr, 1) if mttr is not None else None,
        "mtta_minutes": round(mtta, 1) if mtta is not None else None,
        "last_7_days": sum(1 for i in rows if i.created_at >= week_ago),
        "risk_score": risk_score,
    }
