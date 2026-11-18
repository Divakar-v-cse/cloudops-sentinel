from __future__ import annotations

import math
import shutil

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, or_

from app.api.deps import CurrentUser, DbSession, OperatorUser
from app.models import SecurityFinding
from app.schemas.common import Paginated
from app.schemas.domain import FindingOut, ScanRequest, ScanResult
from app.services import security_scan
from app.services.audit import record_audit

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/findings", response_model=Paginated[FindingOut])
def list_findings(
    db: DbSession,
    user: CurrentUser,
    severity: str | None = None,
    status: str | None = Query(default="open"),
    category: str | None = None,
    source_kind: str | None = None,
    scan_source: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Paginated[FindingOut]:
    query = db.query(SecurityFinding)
    if severity:
        query = query.filter(SecurityFinding.severity == severity)
    if status and status != "all":
        query = query.filter(SecurityFinding.status == status)
    if category:
        query = query.filter(SecurityFinding.category == category)
    if source_kind:
        query = query.filter(SecurityFinding.source_kind == source_kind)
    if scan_source:
        query = query.filter(SecurityFinding.scan_source == scan_source)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                SecurityFinding.title.ilike(like),
                SecurityFinding.resource_name.ilike(like),
                SecurityFinding.description.ilike(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(SecurityFinding.last_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Paginated[FindingOut](
        items=[FindingOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/summary")
def summary(db: DbSession, user: CurrentUser) -> dict:
    data = security_scan.severity_summary(db)
    categories = (
        db.query(SecurityFinding.category, func.count(SecurityFinding.id))
        .filter(SecurityFinding.status == "open")
        .group_by(SecurityFinding.category)
        .order_by(func.count(SecurityFinding.id).desc())
        .all()
    )
    last_scan = (
        db.query(func.max(SecurityFinding.last_seen_at)).scalar()
    )
    return {
        **data,
        "categories": [{"category": c, "count": n} for c, n in categories],
        "last_scan_at": last_scan,
        "findings_total": db.query(func.count(SecurityFinding.id)).scalar() or 0,
    }


@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: int, db: DbSession, user: CurrentUser) -> FindingOut:
    row = db.get(SecurityFinding, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return FindingOut.model_validate(row)


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: int,
    payload: dict,
    db: DbSession,
    operator: OperatorUser,
) -> FindingOut:
    row = db.get(SecurityFinding, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    new_status = payload.get("status")
    if new_status not in {"open", "acknowledged", "resolved", "false_positive"}:
        raise HTTPException(
            status_code=422, detail="status must be open, acknowledged, resolved or false_positive"
        )
    row.status = new_status
    db.commit()
    db.refresh(row)
    record_audit(
        db,
        actor=operator.email,
        action=f"finding.{new_status}",
        entity_type="security_finding",
        entity_id=row.id,
        detail={"finding": row.title},
    )
    return FindingOut.model_validate(row)


@router.post("/scan", response_model=ScanResult)
def run_scan(
    payload: ScanRequest,
    db: DbSession,
    operator: OperatorUser,
) -> ScanResult:
    tools = payload.tools or security_scan.FAST_TOOLS
    unknown = [tool for tool in tools if tool not in security_scan.ALL_TOOLS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown tools: {', '.join(unknown)}")
    result = security_scan.run_scan(
        db,
        tools=tools,
        include_cloud=payload.include_cloud,
        actor=operator.email,
    )
    return ScanResult(**result)


@router.get("/tools")
def tool_status(user: CurrentUser) -> dict:
    import importlib.util

    def available(module: str, binary: str | None = None) -> bool:
        if importlib.util.find_spec(module) is not None:
            return True
        return bool(shutil.which(binary)) if binary else False

    return {
        "tools": [
            {
                "name": "sentinel-iac-rules",
                "kind": "built-in",
                "available": True,
                "purpose": "Terraform and Dockerfile policy checks",
            },
            {
                "name": "aws-config-audit",
                "kind": "built-in",
                "available": True,
                "purpose": "S3, security group and IAM analysis",
            },
            {
                "name": "bandit",
                "kind": "external",
                "available": available("bandit", "bandit"),
                "purpose": "Python static security analysis",
            },
            {
                "name": "pip-audit",
                "kind": "external",
                "available": available("pip_audit", "pip-audit"),
                "purpose": "Python dependency advisories",
            },
            {
                "name": "checkov",
                "kind": "external",
                "available": available("checkov", "checkov"),
                "purpose": "Terraform/Kubernetes misconfiguration",
            },
            {
                "name": "trivy",
                "kind": "external",
                "available": bool(shutil.which("trivy")),
                "purpose": "Container image and filesystem vulnerabilities",
            },
        ],
        "note": "Unavailable tools are reported as skipped by the scanner; no results are invented for them.",
    }


@router.get("/report")
def download_report(
    db: DbSession,
    user: CurrentUser,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    status: str = "open",
    severity: str | None = None,
) -> Response:
    query = db.query(SecurityFinding)
    if status != "all":
        query = query.filter(SecurityFinding.status == status)
    if severity:
        query = query.filter(SecurityFinding.severity == severity)
    rows = query.order_by(SecurityFinding.last_seen_at.desc()).all()
    if format == "csv":
        content = security_scan.export_csv(rows)
        media = "text/csv"
        filename = "cloudops-sentinel-findings.csv"
    else:
        content = security_scan.export_json(db, rows)
        media = "application/json"
        filename = "cloudops-sentinel-findings.json"
    record_audit(
        db,
        actor=user.email,
        action="security.report_downloaded",
        entity_type="security_report",
        detail={"format": format, "findings": len(rows)},
    )
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
