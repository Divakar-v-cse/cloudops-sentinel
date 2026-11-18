"""Infrastructure inventory, telemetry, thresholds, security and cost records."""
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


class InfrastructureInstance(Base, TimestampMixin):
    """A monitored compute resource.

    ``source`` is authoritative about provenance:
      local      -> this host, measured with psutil
      simulated  -> generated telemetry, no real machine behind it
      aws        -> discovered through boto3 from an authorised account
    """

    __tablename__ = "infrastructure_instances"
    __table_args__ = (Index("ix_instances_source_status", "source", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="simulated", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False, index=True)
    instance_type: Mapped[str] = mapped_column(String(60), default="t3.medium")
    region: Mapped[str] = mapped_column(String(40), default="us-east-1")
    environment: Mapped[str] = mapped_column(String(40), default="production", index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False, index=True)
    hostname: Mapped[str | None] = mapped_column(String(160))
    os_name: Mapped[str | None] = mapped_column(String(120))
    private_ip: Mapped[str | None] = mapped_column(String(64))
    public_ip: Mapped[str | None] = mapped_column(String(64))
    cpu_cores: Mapped[int] = mapped_column(Integer, default=2)
    memory_mb: Mapped[int] = mapped_column(Integer, default=4096)
    disk_gb: Mapped[int] = mapped_column(Integer, default=50)
    monthly_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    health_status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)

    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", passive_deletes=True
    )


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        Index("ix_metrics_instance_timestamp", "instance_id", "timestamp"),
        Index("ix_metrics_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("infrastructure_instances.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    cpu_percent: Mapped[float] = mapped_column(Float, default=0.0)
    memory_percent: Mapped[float] = mapped_column(Float, default=0.0)
    disk_percent: Mapped[float] = mapped_column(Float, default=0.0)
    network_in_kbps: Mapped[float] = mapped_column(Float, default=0.0)
    network_out_kbps: Mapped[float] = mapped_column(Float, default=0.0)
    load_avg_1m: Mapped[float] = mapped_column(Float, default=0.0)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    process_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False)

    instance: Mapped[InfrastructureInstance] = relationship(back_populates="metrics")


class Threshold(Base, TimestampMixin):
    """Configurable warning / critical thresholds per metric."""

    __tablename__ = "thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="%")
    warning: Mapped[float] = mapped_column(Float, nullable=False)
    critical: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SecurityFinding(Base):
    __tablename__ = "security_findings"
    __table_args__ = (
        Index("ix_findings_severity_status", "severity", "status"),
        Index("ix_findings_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(240), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="")
    remediation: Mapped[str] = mapped_column(Text, default="")
    scan_source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), default="rule-engine", nullable=False)
    scan_id: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (Index("ix_cost_period_instance", "period", "instance_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("infrastructure_instances.id", ondelete="SET NULL")
    )
    service: Mapped[str] = mapped_column(String(60), default="EC2")
    period: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="simulated", nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PricingAssumption(Base):
    """Editable pricing model used for estimates (never a billing source)."""

    __tablename__ = "pricing_assumptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_type: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    vcpu: Mapped[int] = mapped_column(Integer, default=2)
    memory_gb: Mapped[int] = mapped_column(Integer, default=4)
    hourly_usd: Mapped[float] = mapped_column(Float, nullable=False)
    ebs_gb_usd: Mapped[float] = mapped_column(Float, default=0.08)
    description: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
