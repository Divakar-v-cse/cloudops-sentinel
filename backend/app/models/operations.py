"""Logs, incidents, remediation and deployments."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.models.base import Base, TimestampMixin


class ApplicationLog(Base):
    __tablename__ = "application_logs"
    __table_args__ = (
        Index("ix_logs_service_timestamp", "service", "timestamp"),
        Index("ix_logs_fingerprint", "fingerprint"),
        Index("ix_logs_level_timestamp", "level", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO", nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("infrastructure_instances.id", ondelete="SET NULL")
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    log_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="detected", nullable=False, index=True)
    service: Mapped[str | None] = mapped_column(String(80), index=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("infrastructure_instances.id", ondelete="SET NULL")
    )
    assigned_to: Mapped[str | None] = mapped_column(String(160), index=True)
    detected_by: Mapped[str] = mapped_column(String(60), default="monitoring-engine")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolution_category: Mapped[str | None] = mapped_column(String(60))
    dedupe_key: Mapped[str | None] = mapped_column(String(160), index=True)

    notes: Mapped[list["IncidentNote"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentNote.created_at"
    )


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(30), default="investigation")
    status_change: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    incident: Mapped[Incident] = relationship(back_populates="notes")


class RemediationRule(Base, TimestampMixin):
    __tablename__ = "remediation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(40), default="cpu_percent")
    operator: Mapped[str] = mapped_column(String(8), default=">")
    threshold: Mapped[float] = mapped_column(Float, default=90.0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=5)
    action_name: Mapped[str] = mapped_column(String(60), nullable=False)
    target_scope: Mapped[str] = mapped_column(String(40), default="triggering_instance")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RemediationAction(Base):
    __tablename__ = "remediation_actions"
    __table_args__ = (Index("ix_remediation_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("remediation_rules.id", ondelete="SET NULL")
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL")
    )
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("infrastructure_instances.id", ondelete="SET NULL")
    )
    action_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(160), default="system")
    approved_by: Mapped[str | None] = mapped_column(String(160))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    health_check_before: Mapped[str | None] = mapped_column(String(40))
    health_check_after: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deployments_service_env", "service", "environment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(40), default="production", index=True)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="success", index=True)
    pipeline: Mapped[str] = mapped_column(String(60), default="github-actions")
    stage: Mapped[str] = mapped_column(String(40), default="deploy")
    triggered_by: Mapped[str] = mapped_column(String(120), default="ci-bot")
    source: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
