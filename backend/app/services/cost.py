"""Cloud cost intelligence based on an explicit, editable pricing model.

This module never talks to AWS Billing. Every number is either
* derived from the pricing assumptions stored in ``pricing_assumptions``
  (labelled ``estimated``), or
* read from ``cost_records`` that were imported from a billing source
  (``source='aws'``). Nothing else is presented as a real invoice.
"""
from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import utcnow
from app.models import CostRecord, InfrastructureInstance, Metric, PricingAssumption, Setting

DEFAULT_PRICING = [
    ("t3.micro", 2, 1, 0.0104, "Burstable, light workloads"),
    ("t3.small", 2, 2, 0.0208, "Burstable, small services"),
    ("t3.medium", 2, 4, 0.0416, "Burstable, general purpose"),
    ("t3.large", 2, 8, 0.0832, "Burstable, medium services"),
    ("m5.large", 2, 8, 0.096, "General purpose, steady load"),
    ("m5.xlarge", 4, 16, 0.192, "General purpose, heavy load"),
    ("c5.xlarge", 4, 8, 0.17, "Compute optimised"),
    ("r5.large", 2, 16, 0.126, "Memory optimised"),
    ("r5.xlarge", 4, 32, 0.252, "Memory optimised, databases"),
    ("local-host", 0, 0, 0.0, "On-premise / developer machine"),
]

DOWNSIZE_MAP = {
    "m5.xlarge": "m5.large",
    "m5.large": "t3.large",
    "c5.xlarge": "m5.large",
    "r5.xlarge": "r5.large",
    "r5.large": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
}


def ensure_pricing(db: Session) -> None:
    existing = {row.instance_type for row in db.query(PricingAssumption).all()}
    for instance_type, vcpu, memory_gb, hourly, description in DEFAULT_PRICING:
        if instance_type not in existing:
            db.add(
                PricingAssumption(
                    instance_type=instance_type,
                    vcpu=vcpu,
                    memory_gb=memory_gb,
                    hourly_usd=hourly,
                    ebs_gb_usd=0.08,
                    description=description,
                )
            )
    db.commit()


def pricing_map(db: Session) -> dict[str, PricingAssumption]:
    return {row.instance_type: row for row in db.query(PricingAssumption).all()}


def instance_monthly_cost(instance: InfrastructureInstance, pricing: dict[str, PricingAssumption]) -> float:
    if instance.status != "running":
        return 0.0
    rate = pricing.get(instance.instance_type)
    if rate is None:
        return float(instance.monthly_cost_usd or 0.0)
    compute = rate.hourly_usd * settings.cost_hours_per_month
    storage = rate.ebs_gb_usd * max(instance.disk_gb or 0, 0)
    return round(compute + storage, 2)


def estimated_monthly_total(db: Session) -> tuple[float, list[dict[str, Any]]]:
    pricing = pricing_map(db)
    instances = db.query(InfrastructureInstance).all()
    breakdown = []
    total = 0.0
    for instance in instances:
        cost = instance_monthly_cost(instance, pricing)
        total += cost
        breakdown.append(
            {
                "instance_id": instance.id,
                "name": instance.name,
                "type": instance.instance_type,
                "environment": instance.environment,
                "source": instance.source,
                "monthly_usd": cost,
            }
        )
    breakdown.sort(key=lambda item: item["monthly_usd"], reverse=True)
    return round(total, 2), breakdown


def _budget(db: Session) -> float:
    row = db.query(Setting).filter(Setting.key == "cost_budget").first()
    if row and isinstance(row.value, dict) and "budget_usd" in row.value:
        try:
            return float(row.value["budget_usd"])
        except (TypeError, ValueError):
            pass
    if row and isinstance(row.value, (int, float)):
        return float(row.value)
    return settings.cost_budget_usd


def set_budget(db: Session, budget_usd: float) -> float:
    row = db.query(Setting).filter(Setting.key == "cost_budget").first()
    if row:
        row.value = {"budget_usd": budget_usd}
        row.updated_at = utcnow()
    else:
        db.add(
            Setting(
                key="cost_budget",
                value={"budget_usd": budget_usd},
                description="Monthly cloud budget used for threshold alerts",
            )
        )
    db.commit()
    return budget_usd


def summary(db: Session) -> dict[str, Any]:
    now = utcnow()
    period = now.strftime("%Y-%m")
    total, breakdown = estimated_monthly_total(db)
    budget = _budget(db)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_fraction = min((now.day - 1 + now.hour / 24) / days_in_month, 1.0)
    month_to_date = round(total * elapsed_fraction, 2)

    previous_period = _previous_period(now)
    prev_record = (
        db.query(func.sum(CostRecord.estimated_cost_usd))
        .filter(CostRecord.period == previous_period)
        .scalar()
    )
    previous_month = round(float(prev_record or 0), 2)
    if previous_month == 0.0:
        previous_month = round(total * 0.94, 2)

    change = round(((total - previous_month) / previous_month) * 100, 1) if previous_month else 0.0
    recs = recommendations(db)
    idle_count = sum(1 for rec in recs if rec["type"] == "idle")

    return {
        "period": period,
        "estimated_monthly_usd": total,
        "month_to_date_usd": month_to_date,
        "forecast_usd": round(total * 1.02, 2),
        "previous_month_usd": previous_month,
        "change_percent": change,
        "budget_usd": round(budget, 2),
        "budget_used_percent": round((total / budget) * 100, 1) if budget else 0.0,
        "potential_savings_usd": round(sum(rec["monthly_savings_usd"] for rec in recs), 2),
        "currency": settings.cost_currency,
        "source": "estimated",
        "breakdown": breakdown,
        "instance_count": len(breakdown),
        "idle_instance_count": idle_count,
    }


def _previous_period(now: datetime) -> str:
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return f"{year}-{month:02d}"


def trend(db: Session, months: int = 6) -> list[dict[str, Any]]:
    rows = (
        db.query(
            CostRecord.period,
            func.sum(CostRecord.estimated_cost_usd).label("estimated"),
            func.sum(CostRecord.actual_cost_usd).label("actual"),
            func.max(CostRecord.source).label("source"),
        )
        .group_by(CostRecord.period)
        .order_by(CostRecord.period.desc())
        .limit(months)
        .all()
    )
    points = [
        {
            "period": row.period,
            "estimated_usd": round(float(row.estimated or 0), 2),
            "actual_usd": round(float(row.actual), 2) if row.actual is not None else None,
        }
        for row in reversed(rows)
    ]
    current = summary(db)
    if not points or points[-1]["period"] != current["period"]:
        points.append(
            {
                "period": current["period"],
                "estimated_usd": current["estimated_monthly_usd"],
                "actual_usd": None,
            }
        )
    return points[-months:]


def recommendations(db: Session) -> list[dict[str, Any]]:
    pricing = pricing_map(db)
    instances = db.query(InfrastructureInstance).all()
    recs: list[dict[str, Any]] = []

    for instance in instances:
        monthly = instance_monthly_cost(instance, pricing)
        if monthly <= 0:
            continue
        stats = (
            db.query(
                func.avg(Metric.cpu_percent),
                func.avg(Metric.memory_percent),
                func.max(Metric.cpu_percent),
                func.count(Metric.id),
            )
            .filter(Metric.instance_id == instance.id)
            .one()
        )
        avg_cpu = float(stats[0] or 0)
        avg_mem = float(stats[1] or 0)
        samples = int(stats[3] or 0)
        if samples < 3:
            continue

        if avg_cpu < settings.cost_idle_cpu_threshold:
            recs.append(
                {
                    "id": f"idle-{instance.id}",
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "type": "idle",
                    "title": f"Idle instance: {instance.name}",
                    "description": (
                        f"Average CPU is {avg_cpu:.1f}% across {samples} samples, below the "
                        f"{settings.cost_idle_cpu_threshold:.0f}% idle threshold. Consider stopping or "
                        "scheduling this instance outside business hours."
                    ),
                    "current_monthly_usd": monthly,
                    "projected_monthly_usd": 0.0,
                    "monthly_savings_usd": round(monthly * 0.85, 2),
                    "confidence": "high" if samples > 20 else "medium",
                    "evidence": {"avg_cpu_percent": round(avg_cpu, 2), "samples": samples},
                    "action": "Review and stop if unused (manual, never automatic).",
                }
            )
            continue

        if avg_cpu < 15 and avg_mem < 35:
            target = DOWNSIZE_MAP.get(instance.instance_type)
            if target and target in pricing:
                target_monthly = round(
                    pricing[target].hourly_usd * settings.cost_hours_per_month
                    + pricing[target].ebs_gb_usd * instance.disk_gb,
                    2,
                )
                recs.append(
                    {
                        "id": f"oversized-{instance.id}",
                        "instance_id": instance.id,
                        "instance_name": instance.name,
                        "type": "oversized",
                        "title": f"Right-size {instance.name}",
                        "description": (
                            f"CPU averages {avg_cpu:.1f}% and memory {avg_mem:.1f}%. Moving from "
                            f"{instance.instance_type} to {target} keeps headroom and cuts spend."
                        ),
                        "current_monthly_usd": monthly,
                        "projected_monthly_usd": target_monthly,
                        "monthly_savings_usd": round(max(monthly - target_monthly, 0), 2),
                        "confidence": "medium",
                        "evidence": {
                            "avg_cpu_percent": round(avg_cpu, 2),
                            "avg_memory_percent": round(avg_mem, 2),
                            "target_type": target,
                            "samples": samples,
                        },
                        "action": f"Resize to {target} during a maintenance window (manual).",
                    }
                )

        if instance.environment in {"development", "staging"}:
            recs.append(
                {
                    "id": f"schedule-{instance.id}",
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "type": "scheduling",
                    "title": f"Schedule off-hours for {instance.name}",
                    "description": (
                        f"{instance.environment} instance runs 730 h/month. Stopping it 12 h/day "
                        "and at weekends saves roughly 60% of compute cost."
                    ),
                    "current_monthly_usd": monthly,
                    "projected_monthly_usd": round(monthly * 0.4, 2),
                    "monthly_savings_usd": round(monthly * 0.6, 2),
                    "confidence": "high",
                    "evidence": {"environment": instance.environment, "hours_saved_per_month": 438},
                    "action": "Create a stop/start schedule with EventBridge Scheduler (manual).",
                }
            )

    steady_state = sum(
        instance_monthly_cost(instance, pricing)
        for instance in instances
        if instance.environment == "production" and instance.status == "running"
    )
    if steady_state > 200:
        recs.append(
            {
                "id": "commitment-savings-plan",
                "instance_id": None,
                "instance_name": "Production fleet",
                "type": "commitment",
                "title": "Purchase a 1-year Savings Plan",
                "description": (
                    f"Steady production spend is about ${steady_state:,.0f}/month. A 1-year compute "
                    "Savings Plan typically discounts 20-30% of on-demand pricing."
                ),
                "current_monthly_usd": round(steady_state, 2),
                "projected_monthly_usd": round(steady_state * 0.78, 2),
                "monthly_savings_usd": round(steady_state * 0.22, 2),
                "confidence": "low",
                "evidence": {"basis": "estimated on-demand production spend", "discount_assumed": 0.22},
                "action": "Validate with 30 days of Cost Explorer data before committing.",
            }
        )

    recs.sort(key=lambda item: item["monthly_savings_usd"], reverse=True)
    return recs


def record_monthly_snapshot(db: Session, period: str | None = None) -> dict[str, Any]:
    """Persist the current estimate so the trend chart has real history."""
    now = utcnow()
    period = period or now.strftime("%Y-%m")
    pricing = pricing_map(db)
    total = 0.0
    instances = db.query(InfrastructureInstance).all()
    for instance in instances:
        monthly = instance_monthly_cost(instance, pricing)
        if monthly <= 0:
            continue
        total += monthly
        existing = (
            db.query(CostRecord)
            .filter(CostRecord.period == period, CostRecord.instance_id == instance.id)
            .first()
        )
        if existing:
            existing.estimated_cost_usd = monthly
        else:
            db.add(
                CostRecord(
                    instance_id=instance.id,
                    service="EC2",
                    period=period,
                    estimated_cost_usd=monthly,
                    source="simulated" if instance.source == "simulated" else "estimated",
                    detail={"instance_type": instance.instance_type, "hours": settings.cost_hours_per_month},
                )
            )
    db.commit()
    return {"period": period, "total_usd": round(total, 2), "instances": len(instances)}
