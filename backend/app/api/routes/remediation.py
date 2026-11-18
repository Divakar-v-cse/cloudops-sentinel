from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession, OperatorUser
from app.models import RemediationAction, RemediationRule
from app.schemas.common import Paginated
from app.schemas.domain import (
    ActionCatalogItem,
    ActionOut,
    ActionRequest,
    ApprovalRequest,
    RuleCreate,
    RuleOut,
    RuleUpdate,
)
from app.services import remediation as remediation_service
from app.services.audit import record_audit

router = APIRouter(prefix="/remediation", tags=["remediation"])


@router.get("/catalog", response_model=list[ActionCatalogItem])
def catalog(user: CurrentUser) -> list[ActionCatalogItem]:
    return [ActionCatalogItem(**item) for item in remediation_service.catalog()]


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: DbSession, user: CurrentUser) -> list[RuleOut]:
    rows = db.query(RemediationRule).order_by(RemediationRule.id).all()
    return [RuleOut.model_validate(row) for row in rows]


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(
    payload: RuleCreate,
    db: DbSession,
    operator: OperatorUser,
) -> RuleOut:
    if payload.action_name not in remediation_service.ACTION_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"'{payload.action_name}' is not in the allowlisted action registry",
        )
    rule = RemediationRule(
        name=payload.name,
        description=payload.description,
        metric=payload.metric,
        operator=payload.operator,
        threshold=payload.threshold,
        duration_minutes=payload.duration_minutes,
        action_name=payload.action_name,
        enabled=payload.enabled,
        requires_approval=True,
        dry_run=payload.dry_run,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    record_audit(
        db,
        actor=operator.email,
        action="remediation_rule.created",
        entity_type="remediation_rule",
        entity_id=rule.id,
        detail={"name": rule.name, "action": rule.action_name},
    )
    return RuleOut.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: DbSession,
    operator: OperatorUser,
) -> RuleOut:
    rule = db.get(RemediationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is not None:
            setattr(rule, key, value)
    rule.requires_approval = True  # never relax the approval requirement
    db.commit()
    db.refresh(rule)
    record_audit(
        db,
        actor=operator.email,
        action="remediation_rule.updated",
        entity_type="remediation_rule",
        entity_id=rule.id,
        detail=changes,
    )
    return RuleOut.model_validate(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: DbSession,
    operator: OperatorUser,
) -> dict:
    rule = db.get(RemediationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    record_audit(
        db,
        actor=operator.email,
        action="remediation_rule.deleted",
        entity_type="remediation_rule",
        entity_id=rule_id,
        detail={"name": rule.name},
    )
    return {"deleted": rule_id, "message": "Remediation rule removed"}


@router.get("/actions", response_model=Paginated[ActionOut])
def list_actions(
    db: DbSession,
    user: CurrentUser,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> Paginated[ActionOut]:
    query = db.query(RemediationAction)
    if status:
        query = query.filter(RemediationAction.status == status)
    total = query.count()
    rows = (
        query.order_by(RemediationAction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Paginated[ActionOut](
        items=[ActionOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(math.ceil(total / page_size), 1),
    )


@router.post("/actions", response_model=ActionOut, status_code=201)
def request_action(
    payload: ActionRequest,
    db: DbSession,
    operator: OperatorUser,
) -> ActionOut:
    try:
        action = remediation_service.request_action(
            db,
            action_name=payload.action_name,
            actor=operator.email,
            instance_id=payload.instance_id,
            incident_id=payload.incident_id,
            target=payload.target,
            dry_run=payload.dry_run,
        )
    except remediation_service.RemediationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return ActionOut.model_validate(action)


@router.post("/actions/{action_id}/approve", response_model=ActionOut)
def approve(
    action_id: int,
    payload: ApprovalRequest,
    db: DbSession,
    operator: OperatorUser,
) -> ActionOut:
    action = db.get(RemediationAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    try:
        action = remediation_service.approve(db, action, actor=operator.email, note=payload.note)
    except remediation_service.RemediationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return ActionOut.model_validate(action)


@router.post("/actions/{action_id}/reject", response_model=ActionOut)
def reject(
    action_id: int,
    payload: ApprovalRequest,
    db: DbSession,
    operator: OperatorUser,
) -> ActionOut:
    action = db.get(RemediationAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    try:
        action = remediation_service.reject(db, action, actor=operator.email, reason=payload.note)
    except remediation_service.RemediationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return ActionOut.model_validate(action)


@router.post("/actions/{action_id}/execute", response_model=ActionOut)
def execute_action(
    action_id: int,
    db: DbSession,
    operator: OperatorUser,
) -> ActionOut:
    action = db.get(RemediationAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status not in {"approved", "dry_run"}:
        raise HTTPException(
            status_code=409,
            detail=f"Action is {action.status}; only approved or dry-run actions can be executed",
        )
    try:
        action = remediation_service.execute(db, action, actor=operator.email)
    except remediation_service.RemediationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return ActionOut.model_validate(action)


@router.post("/evaluate")
def evaluate(db: DbSession, operator: OperatorUser) -> dict:
    created = remediation_service.evaluate_rules(db)
    record_audit(
        db,
        actor=operator.email,
        action="remediation.rules_evaluated",
        entity_type="remediation",
        detail={"actions_created": len(created)},
    )
    return {
        "actions_created": len(created),
        "actions": created,
        "message": "Rule evaluation completed",
    }
