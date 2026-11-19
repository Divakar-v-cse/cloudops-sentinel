from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models import InfrastructureInstance
from app.schemas.domain import AwsStatus
from app.services import aws as aws_service
from app.services.audit import record_audit

router = APIRouter(prefix="/aws", tags=["aws integration"])


@router.get("/status", response_model=AwsStatus)
def status(user: CurrentUser) -> AwsStatus:
    return AwsStatus(**aws_service.connection_status())


@router.get("/ec2")
def ec2(db: DbSession, user: CurrentUser) -> dict:
    items = aws_service.list_ec2(db)
    return {
        "items": items,
        "count": len(items),
        "source": items[0]["source"] if items else "simulated",
        "mode": aws_service.connection_status()["mode"],
    }


@router.get("/s3")
def s3(user: CurrentUser) -> dict:
    items = aws_service.list_s3()
    return {
        "items": items,
        "count": len(items),
        "source": items[0]["source"] if items else "simulated",
    }


@router.get("/iam")
def iam(user: CurrentUser) -> dict:
    items = aws_service.list_iam_risks()
    return {
        "items": items,
        "count": len(items),
        "source": items[0]["source"] if items else "simulated",
    }


@router.get("/security-groups")
def security_groups(user: CurrentUser) -> dict:
    items = aws_service.list_security_groups()
    return {
        "items": items,
        "count": len(items),
        "source": items[0]["source"] if items else "simulated",
    }


@router.get("/cloudwatch")
def cloudwatch(
    db: DbSession,
    user: CurrentUser,
    instance_id: str = Query(min_length=1, description="AWS instance id (i-...) or Sentinel instance id"),
    hours: int = Query(default=6, ge=1, le=72),
    metric: str = Query(default="CPUUtilization"),
) -> dict:
    # The UI knows the Sentinel row id, while CloudWatch needs the AWS id.
    # Accept either so callers do not have to resolve it themselves.
    resolved = instance_id
    if instance_id.isdigit():
        row = db.get(InfrastructureInstance, int(instance_id))
        if row is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        if not row.external_id:
            raise HTTPException(
                status_code=422,
                detail="Instance has no AWS instance id; CloudWatch is only available for imported AWS resources",
            )
        resolved = row.external_id
    return aws_service.cloudwatch_metrics(resolved, hours=hours, metric_name=metric)


@router.post("/refresh")
def refresh_status(
    db: DbSession,
    admin: AdminUser,
) -> dict:
    aws_service.reset_status_cache()
    status_payload = aws_service.connection_status(force=True)
    record_audit(
        db,
        actor=admin.email,
        action="aws.connection_checked",
        entity_type="aws",
        detail={"mode": status_payload["mode"]},
    )
    return status_payload


@router.get("/guide")
def guide(user: CurrentUser) -> dict:
    return {
        "current_mode": aws_service.connection_status()["mode"],
        "simulation_env": "AWS_SIMULATION_MODE",
        "steps": [
            "Create a read-only IAM role (SecurityAudit + ReadOnlyAccess + Cost Explorer read).",
            "Attach the role to the instance running CloudOps Sentinel, or export AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in the environment.",
            "Set AWS_REGION and AWS_SIMULATION_MODE=false, then restart the backend.",
            "Verify with GET /api/v1/aws/status - mode should become 'connected'.",
        ],
        "permissions_used": [
            "ec2:DescribeInstances",
            "ec2:DescribeSecurityGroups",
            "s3:ListAllMyBuckets",
            "s3:GetBucketAcl",
            "s3:GetBucketPublicAccessBlock",
            "s3:GetBucketEncryption",
            "s3:GetBucketLocation",
            "iam:ListPolicies",
            "iam:GetPolicyVersion",
            "cloudwatch:GetMetricStatistics",
            "sts:GetCallerIdentity",
            "sns:Publish (optional, only on explicit manual request)",
        ],
        "safety": [
            "No mutating AWS API is implemented in this build.",
            "No credentials are ever stored in the database or logs.",
            "Simulated inventory is always labelled and never merged silently with real data.",
        ],
    }
