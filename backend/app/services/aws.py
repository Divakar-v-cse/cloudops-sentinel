"""Optional AWS integration.

Design rules enforced here:

* Credentials only ever come from the environment / instance role (boto3 default
  chain). Nothing is hardcoded and nothing is written to disk.
* Every payload carries a ``source`` of ``aws`` or ``simulated``; the UI must be
  able to tell the difference.
* When credentials are missing the layer degrades to ``not_configured`` and the
  rest of the product keeps working on local/simulated data.
* No mutating AWS API is ever called. This module is read-only by construction.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from app.core.config import settings
from app.core.utils import utcnow
from app.models import InfrastructureInstance
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STATUS_CACHE: dict[str, Any] = {"at": None, "value": None}
_STATUS_TTL = timedelta(seconds=60)

PUBLIC_CIDRS = {"0.0.0.0/0", "::/0"}
SENSITIVE_PORTS = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB"}


def _client_config() -> Config:
    return Config(
        connect_timeout=settings.aws_connect_timeout,
        read_timeout=settings.aws_connect_timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )


def _session() -> boto3.Session:
    return boto3.Session(region_name=settings.aws_region, profile_name=settings.aws_profile)


def _client(service: str):
    return _session().client(service, config=_client_config())


def has_credentials() -> bool:
    try:
        return _session().get_credentials() is not None
    except (BotoCoreError, Exception):  # pragma: no cover - defensive
        return False


def connection_status(force: bool = False) -> dict[str, Any]:
    now = utcnow()
    if (
        not force
        and _STATUS_CACHE["at"] is not None
        and now - _STATUS_CACHE["at"] < _STATUS_TTL
        and _STATUS_CACHE["value"] is not None
    ):
        return _STATUS_CACHE["value"]

    base = {
        "region": settings.aws_region,
        "checked_at": now,
        "simulation_mode": settings.aws_simulation_mode,
        "account_id": None,
        "identity": None,
    }

    if settings.aws_simulation_mode:
        value = {
            **base,
            "mode": "simulated",
            "connected": False,
            "message": (
                "Simulation mode is enabled (AWS_SIMULATION_MODE=true). "
                "Cloud inventory below is generated sample data, not your account."
            ),
        }
    elif not has_credentials():
        value = {
            **base,
            "mode": "not_configured",
            "connected": False,
            "message": (
                "No AWS credentials found in the environment, shared config or instance role. "
                "Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or attach an IAM role, then set "
                "AWS_SIMULATION_MODE=false."
            ),
        }
    else:
        try:
            identity = _client("sts").get_caller_identity()
            value = {
                **base,
                "mode": "connected",
                "connected": True,
                "account_id": identity.get("Account"),
                "identity": identity.get("Arn"),
                "message": f"Connected to AWS account {identity.get('Account')} in {settings.aws_region}.",
            }
        except (ClientError, BotoCoreError, NoCredentialsError) as exc:
            logger.warning("AWS connection failed: %s", exc)
            value = {
                **base,
                "mode": "error",
                "connected": False,
                "message": f"AWS credentials were found but the API call failed: {exc}",
            }

    _STATUS_CACHE["at"] = now
    _STATUS_CACHE["value"] = value
    return value


def reset_status_cache() -> None:
    _STATUS_CACHE["at"] = None
    _STATUS_CACHE["value"] = None


# ------------------------------------------------------------------- EC2
def list_ec2(db: Session, refresh: bool = False) -> list[dict[str, Any]]:
    status = connection_status()
    if status["mode"] == "connected":
        try:
            ec2 = _client("ec2")
            reservations = ec2.describe_instances().get("Reservations", [])
            items: list[dict[str, Any]] = []
            for reservation in reservations:
                for inst in reservation.get("Instances", []):
                    name = next(
                        (tag["Value"] for tag in inst.get("Tags", []) if tag.get("Key") == "Name"),
                        inst.get("InstanceId", "unnamed"),
                    )
                    items.append(
                        {
                            "resource_id": inst.get("InstanceId"),
                            "name": name,
                            "type": inst.get("InstanceType"),
                            "region": settings.aws_region,
                            "state": (inst.get("State") or {}).get("Name"),
                            "detail": {
                                "private_ip": inst.get("PrivateIpAddress"),
                                "public_ip": inst.get("PublicIpAddress"),
                                "launch_time": inst.get("LaunchTime").isoformat()
                                if inst.get("LaunchTime")
                                else None,
                                "vpc_id": inst.get("VpcId"),
                                "subnet_id": inst.get("SubnetId"),
                                "security_groups": [
                                    sg.get("GroupName") for sg in inst.get("SecurityGroups", [])
                                ],
                                "tags": {t["Key"]: t["Value"] for t in inst.get("Tags", [])},
                            },
                            "source": "aws",
                        }
                    )
            return items
        except (ClientError, BotoCoreError) as exc:
            logger.warning("EC2 inventory failed: %s", exc)

    instances = db.query(InfrastructureInstance).filter(InfrastructureInstance.source != "local").all()
    return [
        {
            "resource_id": inst.external_id or f"i-sim{inst.id:08x}",
            "name": inst.name,
            "type": inst.instance_type,
            "region": inst.region,
            "state": inst.status,
            "detail": {
                "private_ip": inst.private_ip,
                "public_ip": inst.public_ip,
                "environment": inst.environment,
                "note": "simulated inventory",
            },
            "source": "simulated",
        }
        for inst in instances
    ]


# -------------------------------------------------------------------- S3
def list_s3() -> list[dict[str, Any]]:
    status = connection_status()
    if status["mode"] == "connected":
        try:
            s3 = _client("s3")
            buckets = []
            for bucket in s3.list_buckets().get("Buckets", []):
                name = bucket["Name"]
                detail: dict[str, Any] = {
                    "created": bucket["CreationDate"].isoformat() if bucket.get("CreationDate") else None
                }
                try:
                    pab = s3.get_bucket_public_access_block(Bucket=name).get("PublicAccessBlockConfiguration", {})
                    detail["public_access_block"] = pab
                except ClientError as exc:
                    detail["public_access_block"] = None
                    detail["public_access_block_error"] = exc.response.get("Error", {}).get("Code")
                try:
                    acl = s3.get_bucket_acl(Bucket=name)
                    grants = acl.get("Grants", [])
                    detail["public_acl"] = any(
                        (g.get("Grantee") or {}).get("URI", "").endswith("AllUsers") for g in grants
                    )
                except ClientError:
                    detail["public_acl"] = None
                try:
                    enc = s3.get_bucket_encryption(Bucket=name)
                    detail["encryption"] = enc.get("ServerSideEncryptionConfiguration") is not None
                except ClientError as exc:
                    code = exc.response.get("Error", {}).get("Code")
                    detail["encryption"] = False
                    detail["encryption_error"] = code
                try:
                    detail["region"] = s3.get_bucket_location(Bucket=name).get(
                        "LocationConstraint"
                    ) or "us-east-1"
                except ClientError:
                    detail["region"] = settings.aws_region
                buckets.append(
                    {
                        "resource_id": name,
                        "name": name,
                        "type": "s3-bucket",
                        "region": detail.get("region", settings.aws_region),
                        "state": "active",
                        "detail": detail,
                        "source": "aws",
                    }
                )
            return buckets
        except (ClientError, BotoCoreError) as exc:
            logger.warning("S3 inventory failed: %s", exc)

    return _simulated_buckets()


def _simulated_buckets() -> list[dict[str, Any]]:
    specs = [
        ("cloudops-prod-artifacts", True, True, True, False),
        ("cloudops-prod-backups", True, True, True, True),
        ("cloudops-static-assets", False, False, False, False),
        ("cloudops-logs-archive", True, True, False, False),
        ("legacy-app-deployments", True, False, False, False),
    ]
    buckets = []
    for name, block_public, encryption, versioning, public_acl in specs:
        buckets.append(
            {
                "resource_id": name,
                "name": name,
                "type": "s3-bucket",
                "region": settings.aws_region,
                "state": "active",
                "detail": {
                    "public_access_block": {
                        "BlockPublicAcls": block_public,
                        "IgnorePublicAcls": block_public,
                        "BlockPublicPolicy": block_public,
                        "RestrictPublicBuckets": block_public,
                    },
                    "encryption": encryption,
                    "versioning": versioning,
                    "public_acl": public_acl,
                    "note": "simulated inventory",
                },
                "source": "simulated",
            }
        )
    return buckets


# ------------------------------------------------------------------- IAM
def list_iam_risks() -> list[dict[str, Any]]:
    status = connection_status()
    if status["mode"] != "connected":
        return _simulated_iam_risks()
    findings: list[dict[str, Any]] = []
    try:
        iam = _client("iam")
        paginator = iam.get_paginator("list_policies")
        for page in paginator.paginate(Scope="Local"):
            for policy in page.get("Policies", []):
                version_id = policy.get("DefaultVersionId")
                if not version_id:
                    continue
                try:
                    version = iam.get_policy_version(
                        PolicyArn=policy["Arn"], VersionId=version_id
                    )["PolicyVersion"]
                except (ClientError, BotoCoreError):
                    continue
                document = version.get("Document", {})
                statements = document.get("Statement", [])
                if isinstance(statements, dict):
                    statements = [statements]
                issues = []
                for statement in statements:
                    if statement.get("Effect") != "Allow":
                        continue
                    actions = statement.get("Action", [])
                    actions = [actions] if isinstance(actions, str) else actions
                    resources = statement.get("Resource", [])
                    resources = [resources] if isinstance(resources, str) else resources
                    if "*" in actions and "*" in resources:
                        issues.append("Allow * on * (full administrator)")
                    elif any(a.endswith("*") for a in actions) and "*" in resources:
                        issues.append(f"Wildcard actions {actions} on all resources")
                    if "iam:*" in actions or "iam:PassRole" in actions:
                        issues.append("Privilege-escalation capable IAM permissions")
                if issues:
                    findings.append(
                        {
                            "resource_id": policy["Arn"],
                            "name": policy["PolicyName"],
                            "type": "iam-policy",
                            "region": "global",
                            "state": "active",
                            "detail": {
                                "issues": sorted(set(issues)),
                                "statement_count": len(statements),
                                "attached_users": policy.get("AttachmentCount", 0),
                            },
                            "source": "aws",
                        }
                    )
    except (ClientError, BotoCoreError) as exc:
        logger.warning("IAM analysis failed: %s", exc)
    return findings


def _simulated_iam_risks() -> list[dict[str, Any]]:
    return [
        {
            "resource_id": "arn:aws:iam::000000000000:policy/CloudOpsLegacyAdmin",
            "name": "CloudOpsLegacyAdmin",
            "type": "iam-policy",
            "region": "global",
            "state": "active",
            "detail": {
                "issues": ["Allow * on * (full administrator)"],
                "statement_count": 2,
                "attached_users": 3,
                "note": "simulated inventory",
            },
            "source": "simulated",
        },
        {
            "resource_id": "arn:aws:iam::000000000000:policy/DeployPipelineRole",
            "name": "DeployPipelineRole",
            "type": "iam-policy",
            "region": "global",
            "state": "active",
            "detail": {
                "issues": ["Privilege-escalation capable IAM permissions (iam:PassRole)"],
                "statement_count": 4,
                "attached_users": 1,
                "note": "simulated inventory",
            },
            "source": "simulated",
        },
    ]


# -------------------------------------------------------- security groups
def list_security_groups() -> list[dict[str, Any]]:
    status = connection_status()
    if status["mode"] != "connected":
        return _simulated_security_groups()
    groups: list[dict[str, Any]] = []
    try:
        ec2 = _client("ec2")
        for sg in ec2.describe_security_groups().get("SecurityGroups", []):
            groups.append(
                {
                    "resource_id": sg.get("GroupId"),
                    "name": sg.get("GroupName"),
                    "type": "security-group",
                    "region": settings.aws_region,
                    "state": "active",
                    "detail": {
                        "description": sg.get("Description"),
                        "vpc_id": sg.get("VpcId"),
                        "ingress": [
                            {
                                "protocol": rule.get("IpProtocol"),
                                "from_port": rule.get("FromPort"),
                                "to_port": rule.get("ToPort"),
                                "cidrs": [r.get("CidrIp") for r in rule.get("IpRanges", [])]
                                + [r.get("CidrIpv6") for r in rule.get("Ipv6Ranges", [])],
                            }
                            for rule in sg.get("IpPermissions", [])
                        ],
                    },
                    "source": "aws",
                }
            )
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Security group inventory failed: %s", exc)
    return groups


def _simulated_security_groups() -> list[dict[str, Any]]:
    return [
        {
            "resource_id": "sg-0a1b2c3d4e5f60001",
            "name": "legacy-ssh-open",
            "type": "security-group",
            "region": settings.aws_region,
            "state": "active",
            "detail": {
                "description": "simulated legacy bastion group",
                "vpc_id": "vpc-sim00001",
                "ingress": [
                    {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidrs": ["0.0.0.0/0"]},
                    {"protocol": "tcp", "from_port": 3389, "to_port": 3389, "cidrs": ["0.0.0.0/0"]},
                ],
                "note": "simulated inventory",
            },
            "source": "simulated",
        },
        {
            "resource_id": "sg-0a1b2c3d4e5f60002",
            "name": "api-public-alb",
            "type": "security-group",
            "region": settings.aws_region,
            "state": "active",
            "detail": {
                "description": "simulated public load balancer",
                "vpc_id": "vpc-sim00001",
                "ingress": [
                    {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidrs": ["0.0.0.0/0"]},
                ],
                "note": "simulated inventory",
            },
            "source": "simulated",
        },
        {
            "resource_id": "sg-0a1b2c3d4e5f60003",
            "name": "internal-db",
            "type": "security-group",
            "region": settings.aws_region,
            "state": "active",
            "detail": {
                "description": "simulated database group",
                "vpc_id": "vpc-sim00001",
                "ingress": [
                    {"protocol": "tcp", "from_port": 5432, "to_port": 5432, "cidrs": ["0.0.0.0/0"]},
                ],
                "note": "simulated inventory",
            },
            "source": "simulated",
        },
    ]


# ------------------------------------------------------------- CloudWatch
def cloudwatch_metrics(instance_id: str, hours: int = 6, metric_name: str = "CPUUtilization") -> dict[str, Any]:
    status = connection_status()
    if status["mode"] != "connected":
        return {
            "source": "simulated",
            "metric": metric_name,
            "instance_id": instance_id,
            "datapoints": [],
            "message": "CloudWatch is only queried in connected mode. Simulated telemetry lives in the Monitoring module.",
        }
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    try:
        cw = _client("cloudwatch")
        response = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName=metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start,
            EndTime=end,
            Period=300,
            Statistics=["Average", "Maximum"],
        )
        points = sorted(
            [
                {
                    "timestamp": dp["Timestamp"].isoformat(),
                    "average": round(dp.get("Average", 0), 2),
                    "maximum": round(dp.get("Maximum", 0), 2),
                }
                for dp in response.get("Datapoints", [])
            ],
            key=lambda item: item["timestamp"],
        )
        return {"source": "aws", "metric": metric_name, "instance_id": instance_id, "datapoints": points}
    except (ClientError, BotoCoreError) as exc:
        return {
            "source": "aws",
            "error": str(exc),
            "metric": metric_name,
            "instance_id": instance_id,
            "datapoints": [],
        }


# ------------------------------------------------------------------- SNS
def publish_sns(subject: str, message: str) -> dict[str, Any]:
    """Optional outbound notification. Never called automatically for alerts."""
    if not settings.sns_topic_arn:
        return {"published": False, "reason": "SNS_TOPIC_ARN is not configured"}
    if connection_status()["mode"] != "connected":
        return {"published": False, "reason": "AWS is not connected (simulation mode or missing credentials)"}
    try:
        _client("sns").publish(
            TopicArn=settings.sns_topic_arn, Subject=subject[:100], Message=message
        )
        return {"published": True}
    except (ClientError, BotoCoreError) as exc:
        return {"published": False, "reason": str(exc)}


def fingerprint(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]
