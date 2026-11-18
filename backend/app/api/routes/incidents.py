from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_

from app.api.deps import AnalystUser, CurrentUser, DbSession
from app.core.utils import utcnow
from app.models import Incident
from app.schemas.common import Paginated
from app.schemas.domain import (
    IncidentCreate,
    IncidentDetail,
    IncidentNoteCreate,
    IncidentNoteOut,
    IncidentOut,
    IncidentStatusChange,
    IncidentUpdate,
)
from app.services import incidents as incident_service
from app.services.audit import record_audit

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=Paginated[IncidentOut])
def list_incidents(
    db: DbSession,
    user: CurrentUser,
    status: str | None = None,
    severity: str | None = None,
    service: str | None = None,
    assigned_to: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Paginated[IncidentOut]:
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if severity:
        query = query.filter(Incident.severity == severity)
    if service:
        query = query.filter(Incident.service == service)
    if assigned_to:
        query = query.filter(Incident.assigned_to == assigned_to)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Incident.title.ilike(like),
                Incident.incident_number.ilike(like),
                Incident.description.ilike(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(Incident.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Paginated[IncidentOut](
        items=[IncidentOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/stats")
def stats(db: DbSession, user: CurrentUser) -> dict:
    return incident_service.statistics(db)


@router.post("", response_model=IncidentDetail, status_code=201)
def create(
    payload: IncidentCreate,
    db: DbSession,
    analyst: AnalystUser,
) -> IncidentDetail:
    incident = incident_service.create_incident(
        db,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        service=payload.service,
        instance_id=payload.instance_id,
        assigned_to=payload.assigned_to,
        detected_by=payload.detected_by,
        actor=analyst.email,
    )
    record_audit(
        db,
        actor=analyst.email,
        action="incident.created_manual",
        entity_type="incident",
        entity_id=incident.id,
        detail={"severity": payload.severity},
    )
    return _detail(db, incident)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get(incident_id: int, db: DbSession, user: CurrentUser) -> IncidentDetail:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _detail(db, incident)


def _detail(db, incident: Incident) -> IncidentDetail:
    from app.schemas.domain import IncidentNoteOut as NoteSchema

    end = incident.resolved_at or (utcnow() if incident.status in {"detected", "acknowledged", "investigating"} else None)
    duration = int((end - incident.created_at).total_seconds() / 60) if end else None
    payload = IncidentOut.model_validate(incident).model_dump()
    return IncidentDetail(
        **payload,
        notes=[NoteSchema.model_validate(note) for note in incident.notes],
        duration_minutes=duration,
    )


@router.patch("/{incident_id}", response_model=IncidentDetail)
def update(
    incident_id: int,
    payload: IncidentUpdate,
    db: DbSession,
    analyst: AnalystUser,
) -> IncidentDetail:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    changes = payload.model_dump(exclude_unset=True)
    if "severity" in changes and changes["severity"]:
        incident.severity = changes["severity"]
    if "assigned_to" in changes:
        incident.assigned_to = changes["assigned_to"]
    if "service" in changes:
        incident.service = changes["service"]
    if "title" in changes and changes["title"]:
        incident.title = changes["title"][:240]
    incident.updated_at = utcnow()
    db.commit()
    db.refresh(incident)
    record_audit(
        db,
        actor=analyst.email,
        action="incident.updated",
        entity_type="incident",
        entity_id=incident.id,
        detail=changes,
    )
    return _detail(db, incident)


@router.post("/{incident_id}/status", response_model=IncidentDetail)
def change_status(
    incident_id: int,
    payload: IncidentStatusChange,
    db: DbSession,
    analyst: AnalystUser,
) -> IncidentDetail:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        incident_service.change_status(
            db,
            incident,
            new_status=payload.status,
            actor=analyst.email,
            note=payload.note,
            resolution_summary=payload.resolution_summary,
            resolution_category=payload.resolution_category,
        )
    except incident_service.IncidentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    db.refresh(incident)
    return _detail(db, incident)


@router.post("/{incident_id}/notes", response_model=IncidentNoteOut, status_code=201)
def add_note(
    incident_id: int,
    payload: IncidentNoteCreate,
    db: DbSession,
    analyst: AnalystUser,
) -> IncidentNoteOut:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    note = incident_service.add_note(
        db,
        incident,
        author=analyst.email,
        note=payload.note,
        note_type=payload.note_type,
    )
    record_audit(
        db,
        actor=analyst.email,
        action="incident.note_added",
        entity_type="incident",
        entity_id=incident.id,
        detail={"note_type": payload.note_type},
    )
    return IncidentNoteOut.model_validate(note)


@router.get("/{incident_id}/timeline", response_model=list[IncidentNoteOut])
def timeline(incident_id: int, db: DbSession, user: CurrentUser) -> list[IncidentNoteOut]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return [IncidentNoteOut.model_validate(note) for note in incident.notes]
