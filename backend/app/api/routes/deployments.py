from __future__ import annotations

import math
from datetime import timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, OperatorUser
from app.core.utils import utcnow
from app.models import Deployment
from app.schemas.common import Paginated
from app.schemas.domain import DeploymentOut, PipelineOut
from app.services import deployments as deployment_service
from app.services.audit import record_audit
from app.services.notifications import notify

router = APIRouter(tags=["deployments"])


class DeploymentIngest(BaseModel):
    service: str = Field(min_length=1, max_length=80)
    environment: str = "production"
    version: str = Field(min_length=1, max_length=60)
    status: str = "success"
    commit_sha: str | None = None
    pipeline: str = "external-ci"
    stage: str = "deploy"
    duration_seconds: int = 0
    triggered_by: str = "ci-bot"
    detail: dict = {}


@router.get("/deployments", response_model=Paginated[DeploymentOut])
def list_deployments(
    db: DbSession,
    user: CurrentUser,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Paginated[DeploymentOut]:
    query = db.query(Deployment)
    if service:
        query = query.filter(Deployment.service == service)
    if environment:
        query = query.filter(Deployment.environment == environment)
    if status:
        query = query.filter(Deployment.status == status)
    total = query.count()
    rows = (
        query.order_by(Deployment.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Paginated[DeploymentOut](
        items=[DeploymentOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.get("/deployments/summary")
def summary(db: DbSession, user: CurrentUser) -> dict:
    return deployment_service.summary(db)


@router.post("/deployments", response_model=DeploymentOut, status_code=201)
def ingest_deployment(
    payload: DeploymentIngest,
    db: DbSession,
    operator: OperatorUser,
) -> DeploymentOut:
    finished = utcnow()
    row = Deployment(
        service=payload.service,
        environment=payload.environment,
        version=payload.version,
        commit_sha=payload.commit_sha,
        status=payload.status,
        pipeline=payload.pipeline,
        stage=payload.stage,
        triggered_by=payload.triggered_by,
        source="pipeline",
        duration_seconds=payload.duration_seconds,
        started_at=finished - timedelta(seconds=payload.duration_seconds),
        finished_at=finished,
        detail=payload.detail,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit(
        db,
        actor=operator.email,
        action="deployment.recorded",
        entity_type="deployment",
        entity_id=row.id,
        detail={
            "service": row.service,
            "version": row.version,
            "status": row.status,
            "source": "pipeline",
        },
    )
    if row.status == "failed":
        notify(
            db,
            title=f"Deployment failed: {row.service} {row.version}",
            message=f"{row.service} {row.version} failed in {row.environment} at stage {row.stage}.",
            severity="warning",
            category="deployment",
            entity_type="deployment",
            entity_id=row.id,
        )
    return DeploymentOut.model_validate(row)


@router.get("/pipelines", response_model=list[PipelineOut])
def pipelines(db: DbSession, user: CurrentUser) -> list[PipelineOut]:
    return [PipelineOut(**item) for item in deployment_service.pipelines(db)]
