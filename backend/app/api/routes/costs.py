from __future__ import annotations


from fastapi import APIRouter, HTTPException

from app.api.deps import AdminUser, CurrentUser, DbSession, OperatorUser
from app.models import PricingAssumption
from app.schemas.domain import (
    BudgetUpdate,
    CostRecommendation,
    CostSummary,
    CostTrendPoint,
    PricingOut,
)
from app.services import cost as cost_service
from app.services.audit import record_audit

router = APIRouter(prefix="/costs", tags=["cost optimization"])


@router.get("/summary", response_model=CostSummary)
def summary(db: DbSession, user: CurrentUser) -> CostSummary:
    return CostSummary(**cost_service.summary(db))


@router.get("/trend", response_model=list[CostTrendPoint])
def trend(db: DbSession, user: CurrentUser, months: int = 6) -> list[CostTrendPoint]:
    return [CostTrendPoint(**point) for point in cost_service.trend(db, months=months)]


@router.get("/recommendations", response_model=list[CostRecommendation])
def recommendations(db: DbSession, user: CurrentUser) -> list[CostRecommendation]:
    return [CostRecommendation(**rec) for rec in cost_service.recommendations(db)]


@router.get("/pricing", response_model=list[PricingOut])
def pricing(db: DbSession, user: CurrentUser) -> list[PricingOut]:
    return [PricingOut.model_validate(row) for row in db.query(PricingAssumption).order_by(PricingAssumption.instance_type)]


@router.patch("/pricing/{instance_type}", response_model=PricingOut)
def update_pricing(
    instance_type: str,
    payload: dict,
    db: DbSession,
    admin: AdminUser,
) -> PricingOut:
    row = (
        db.query(PricingAssumption)
        .filter(PricingAssumption.instance_type == instance_type)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No pricing assumption for '{instance_type}'")
    if "hourly_usd" in payload:
        try:
            hourly = float(payload["hourly_usd"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="hourly_usd must be a number") from None
        if hourly < 0:
            raise HTTPException(status_code=422, detail="hourly_usd cannot be negative")
        row.hourly_usd = hourly
    if "ebs_gb_usd" in payload:
        row.ebs_gb_usd = float(payload["ebs_gb_usd"])
    db.commit()
    db.refresh(row)
    record_audit(
        db,
        actor=admin.email,
        action="pricing.updated",
        entity_type="pricing",
        entity_id=row.instance_type,
        detail={"hourly_usd": row.hourly_usd, "ebs_gb_usd": row.ebs_gb_usd},
    )
    return PricingOut.model_validate(row)


@router.put("/budget", response_model=dict)
def update_budget(
    payload: BudgetUpdate,
    db: DbSession,
    admin: AdminUser,
) -> dict:
    budget = cost_service.set_budget(db, payload.budget_usd)
    record_audit(
        db,
        actor=admin.email,
        action="cost_budget.updated",
        entity_type="settings",
        entity_id="cost_budget",
        detail={"budget_usd": budget},
    )
    return {"budget_usd": budget, "message": "Budget updated"}


@router.post("/snapshot")
def snapshot(
    db: DbSession,
    operator: OperatorUser,
) -> dict:
    result = cost_service.record_monthly_snapshot(db)
    record_audit(
        db,
        actor=operator.email,
        action="cost.snapshot",
        entity_type="cost_record",
        detail=result,
    )
    return {**result, "note": "Estimated from the stored pricing model, not an AWS invoice."}
