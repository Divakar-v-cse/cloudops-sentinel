from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _validate_email(value: str) -> str:
    """Permissive email validation.

    Internal deployments legitimately use reserved TLDs such as ``.local`` or
    ``.internal``, so we validate shape rather than public deliverability.
    """
    value = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("must be a valid email address")
    return value


EmailAddress = Annotated[str, AfterValidator(_validate_email)]


# ---------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=200)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class RoleOut(ORMModel):
    id: int
    name: str
    description: str | None = None


class UserOut(ORMModel):
    id: int
    email: EmailAddress
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseModel):
    email: EmailAddress
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "engineer", "analyst", "viewer"] = "viewer"


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------- instances
class InstanceOut(ORMModel):
    id: int
    name: str
    external_id: str | None = None
    provider: str
    source: str
    instance_type: str
    region: str
    environment: str
    status: str
    hostname: str | None = None
    os_name: str | None = None
    private_ip: str | None = None
    public_ip: str | None = None
    cpu_cores: int
    memory_mb: int
    disk_gb: int
    monthly_cost_usd: float
    tags: dict[str, Any] = {}
    health_status: str
    last_seen_at: datetime | None = None


class InstanceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    instance_type: str = "t3.medium"
    region: str = "us-east-1"
    environment: Literal["production", "staging", "development"] = "development"
    cpu_cores: int = Field(default=2, ge=1, le=256)
    memory_mb: int = Field(default=4096, ge=512)
    disk_gb: int = Field(default=50, ge=8)
    simulate: bool = True
    tags: dict[str, Any] = {}


class InstanceUpdate(BaseModel):
    name: str | None = None
    environment: str | None = None
    assigned_team: str | None = None
    tags: dict[str, Any] | None = None


# ----------------------------------------------------------- metrics
class MetricOut(ORMModel):
    id: int
    instance_id: int
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_in_kbps: float
    network_out_kbps: float
    load_avg_1m: float
    uptime_seconds: int
    process_count: int
    source: str


class MetricPoint(BaseModel):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_in_kbps: float
    network_out_kbps: float


class ThresholdOut(ORMModel):
    id: int
    metric: str
    display_name: str
    unit: str
    warning: float
    critical: float
    enabled: bool


class ThresholdUpdate(BaseModel):
    warning: float | None = None
    critical: float | None = None
    enabled: bool | None = None

    @field_validator("critical")
    @classmethod
    def _positive(cls, value):
        if value is not None and value <= 0:
            raise ValueError("critical threshold must be positive")
        return value


class AlertOut(BaseModel):
    instance_id: int
    instance_name: str
    metric: str
    value: float
    threshold: float
    level: Literal["warning", "critical"]
    message: str
    timestamp: datetime
    source: str


# ---------------------------------------------------------- security
class FindingOut(ORMModel):
    id: int
    finding_key: str
    title: str
    severity: str
    category: str
    resource_name: str
    resource_type: str
    description: str
    evidence: str
    remediation: str
    scan_source: str
    source_kind: str
    scan_id: str | None = None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


class ScanRequest(BaseModel):
    tools: list[str] | None = None
    include_cloud: bool = True
    resolve_missing: bool = False


class ToolStatus(BaseModel):
    tool: str
    status: Literal["executed", "skipped", "failed"]
    reason: str | None = None
    findings: int = 0
    duration_ms: int = 0


class ScanResult(BaseModel):
    scan_id: str
    started_at: datetime
    finished_at: datetime
    findings_created: int
    findings_updated: int
    findings_resolved: int
    tools: list[ToolStatus]
    simulated_resources: bool
    aws_connected: bool


# -------------------------------------------------------------- cost
class CostSummary(BaseModel):
    period: str
    estimated_monthly_usd: float
    month_to_date_usd: float
    forecast_usd: float
    previous_month_usd: float
    change_percent: float
    budget_usd: float
    budget_used_percent: float
    potential_savings_usd: float
    currency: str
    source: str
    breakdown: list[dict[str, Any]]
    instance_count: int
    idle_instance_count: int


class CostTrendPoint(BaseModel):
    period: str
    estimated_usd: float
    actual_usd: float | None = None


class CostRecommendation(BaseModel):
    id: str
    instance_id: int | None
    instance_name: str
    type: Literal["idle", "oversized", "unattached_storage", "commitment", "scheduling"]
    title: str
    description: str
    current_monthly_usd: float
    projected_monthly_usd: float
    monthly_savings_usd: float
    confidence: Literal["low", "medium", "high"]
    evidence: dict[str, Any]
    action: str


class PricingOut(ORMModel):
    id: int
    instance_type: str
    vcpu: int
    memory_gb: int
    hourly_usd: float
    ebs_gb_usd: float
    description: str | None = None


class BudgetUpdate(BaseModel):
    budget_usd: float = Field(gt=0)


# -------------------------------------------------------------- logs
class LogIngestItem(BaseModel):
    service: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=8000)
    level: str = "INFO"
    timestamp: datetime | None = None
    instance: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = {}


class LogIngestRequest(BaseModel):
    logs: list[LogIngestItem] = Field(min_length=1, max_length=500)


class LogOut(ORMModel):
    id: int
    service: str
    level: str
    severity: str
    message: str
    timestamp: datetime
    fingerprint: str
    trace_id: str | None = None
    instance_id: int | None = None
    log_metadata: dict[str, Any] = Field(default={}, alias="log_metadata")


class LogGroup(BaseModel):
    fingerprint: str
    service: str
    severity: str
    sample_message: str
    count: int
    first_seen: datetime
    last_seen: datetime
    affected_traces: int


class LogAnalysis(BaseModel):
    source: Literal["ai", "rule-based"]
    summary: str
    likely_causes: list[str]
    hypotheses: list[dict[str, Any]]
    debug_commands: list[str]
    next_steps: list[str]
    confidence: Literal["low", "medium", "high"]
    disclaimer: str
    related_incidents: list[dict[str, Any]] = []


# --------------------------------------------------------- incidents
class IncidentOut(ORMModel):
    id: int
    incident_number: str
    title: str
    description: str
    severity: str
    status: str
    service: str | None = None
    instance_id: int | None = None
    assigned_to: str | None = None
    detected_by: str
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    resolution_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class IncidentNoteOut(ORMModel):
    id: int
    incident_id: int
    author: str
    note: str
    note_type: str
    status_change: str | None = None
    created_at: datetime


class IncidentDetail(IncidentOut):
    notes: list[IncidentNoteOut] = []
    duration_minutes: int | None = None


class IncidentCreate(BaseModel):
    title: str = Field(min_length=4, max_length=240)
    description: str = ""
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    service: str | None = None
    instance_id: int | None = None
    assigned_to: str | None = None
    detected_by: str = "manual"


class IncidentUpdate(BaseModel):
    severity: Literal["critical", "high", "medium", "low"] | None = None
    assigned_to: str | None = None
    service: str | None = None
    title: str | None = None


class IncidentStatusChange(BaseModel):
    status: Literal["acknowledged", "investigating", "resolved", "closed", "reopened"]
    note: str | None = None
    resolution_summary: str | None = None
    resolution_category: str | None = None


class IncidentNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    note_type: Literal["investigation", "comment", "action", "resolution"] = "investigation"


# ------------------------------------------------------- remediation
class RuleOut(ORMModel):
    id: int
    name: str
    description: str
    metric: str
    operator: str
    threshold: float
    duration_minutes: int
    action_name: str
    target_scope: str
    enabled: bool
    requires_approval: bool
    dry_run: bool


class RuleCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = ""
    metric: Literal["cpu_percent", "memory_percent", "disk_percent", "network_in_kbps"] = "cpu_percent"
    operator: Literal[">", ">=", "<", "<="] = ">"
    threshold: float = Field(gt=0)
    duration_minutes: int = Field(default=5, ge=1, le=240)
    action_name: str
    enabled: bool = True
    requires_approval: bool = True
    dry_run: bool = True


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold: float | None = None
    dry_run: bool | None = None
    requires_approval: bool | None = None


class ActionOut(ORMModel):
    id: int
    rule_id: int | None = None
    incident_id: int | None = None
    instance_id: int | None = None
    action_name: str
    target: str
    status: str
    dry_run: bool
    requested_by: str
    approved_by: str | None = None
    rejection_reason: str | None = None
    output: str | None = None
    error: str | None = None
    health_check_before: str | None = None
    health_check_after: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    executed_at: datetime | None = None


class ActionRequest(BaseModel):
    action_name: str
    instance_id: int | None = None
    incident_id: int | None = None
    target: str | None = None
    dry_run: bool = True
    reason: str | None = None


class ApprovalRequest(BaseModel):
    note: str | None = None


class ActionCatalogItem(BaseModel):
    name: str
    label: str
    description: str
    risk: Literal["low", "medium", "high"]
    destructive: bool
    requires_approval: bool
    supports_dry_run: bool
    categories: list[str]


# ------------------------------------------------------- deployments
class DeploymentOut(ORMModel):
    id: int
    service: str
    environment: str
    version: str
    commit_sha: str | None = None
    status: str
    pipeline: str
    stage: str
    triggered_by: str
    source: str
    duration_seconds: int
    started_at: datetime
    finished_at: datetime | None = None
    detail: dict[str, Any] = {}


class PipelineOut(BaseModel):
    name: str
    platform: str
    config_path: str
    detected: bool
    last_run: DeploymentOut | None = None
    success_rate: float
    total_runs: int
    stages: list[str]


# --------------------------------------------------------------- aws
class AwsStatus(BaseModel):
    mode: Literal["simulated", "connected", "not_configured", "error"]
    connected: bool
    region: str
    account_id: str | None = None
    identity: str | None = None
    message: str
    checked_at: datetime
    simulation_mode: bool


class AwsResource(BaseModel):
    resource_id: str
    name: str
    type: str
    region: str
    state: str | None = None
    detail: dict[str, Any] = {}
    source: Literal["aws", "simulated"]


# ------------------------------------------------------------- audit
class AuditOut(ORMModel):
    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str | None = None
    detail: dict[str, Any] = {}
    ip_address: str | None = None
    created_at: datetime


class NotificationOut(ORMModel):
    id: int
    title: str
    message: str
    severity: str
    category: str
    is_read: bool
    entity_type: str | None = None
    entity_id: str | None = None
    created_at: datetime


Token.model_rebuild()
