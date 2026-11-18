"""Deployment history and CI/CD pipeline visibility.

Pipeline *definitions* are detected from the files that exist in this repository.
Pipeline *runs* come from the ``deployments`` table; seeded rows are marked
``source='simulated'`` while rows posted by a real pipeline are ``source='pipeline'``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.core.utils import utcnow
from app.models import Deployment

PIPELINE_DEFINITIONS = [
    {
        "name": "sentinel-ci",
        "platform": "github-actions",
        "config_path": ".github/workflows/ci.yml",
        "stages": [
            "backend-lint",
            "backend-tests",
            "frontend-build",
            "dependency-audit",
            "docker-build",
            "trivy-scan",
            "terraform-validate",
        ],
    },
    {
        "name": "sentinel-release",
        "platform": "github-actions",
        "config_path": ".github/workflows/release.yml",
        "stages": ["build-and-push", "provision-check", "deploy-staging", "smoke-test", "deploy-production"],
    },
    {
        "name": "sentinel-jenkins",
        "platform": "jenkins",
        "config_path": "Jenkinsfile",
        "stages": ["checkout", "build", "test", "docker-image", "security-scan", "deploy-with-approval"],
    },
    {
        "name": "sentinel-infrastructure",
        "platform": "terraform",
        "config_path": "infrastructure/terraform",
        "stages": ["fmt-check", "validate", "plan", "apply-with-approval"],
    },
]


def pipelines(db: Session) -> list[dict[str, Any]]:
    output = []
    for definition in PIPELINE_DEFINITIONS:
        path = Path(REPO_ROOT) / definition["config_path"]
        detected = path.exists()
        runs = (
            db.query(Deployment)
            .filter(Deployment.pipeline == definition["name"])
            .order_by(Deployment.started_at.desc())
            .all()
        )
        total = len(runs)
        successes = sum(1 for run in runs if run.status == "success")
        output.append(
            {
                "name": definition["name"],
                "platform": definition["platform"],
                "config_path": definition["config_path"],
                "detected": detected,
                "last_run": runs[0] if runs else None,
                "success_rate": round((successes / total) * 100, 1) if total else 0.0,
                "total_runs": total,
                "stages": definition["stages"],
            }
        )
    return output


def summary(db: Session) -> dict[str, Any]:
    since = utcnow()
    total = db.query(func.count(Deployment.id)).scalar() or 0
    success = (
        db.query(func.count(Deployment.id)).filter(Deployment.status == "success").scalar() or 0
    )
    failed = db.query(func.count(Deployment.id)).filter(Deployment.status == "failed").scalar() or 0
    last = db.query(Deployment).order_by(Deployment.started_at.desc()).first()
    week = db.query(func.count(Deployment.id)).filter(
        Deployment.started_at >= since.replace(day=max(since.day - 7, 1))
    ).scalar() or 0
    return {
        "total_deployments": total,
        "successful": success,
        "failed": failed,
        "success_rate": round((success / total) * 100, 1) if total else 0.0,
        "last_deployment": {
            "service": last.service,
            "version": last.version,
            "status": last.status,
            "environment": last.environment,
            "started_at": last.started_at,
            "source": last.source,
        }
        if last
        else None,
        "deployments_last_7_days": week,
    }
