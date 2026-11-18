"""Security scanning orchestration.

Honesty rules:
* External scanners are executed as subprocesses. If a tool is not installed the
  result is reported as ``skipped`` with a reason - we never invent its output.
* Findings generated from the simulated AWS inventory are stored with
  ``source_kind='simulated'`` and their description says so.
* The built-in policy engine only reasons about files that actually exist in
  this repository (Terraform HCL, Dockerfiles).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.core.utils import utcnow
from app.models import SecurityFinding
from app.services import aws as aws_service
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(REPO_ROOT) / "backend"
INFRA_DIR = Path(REPO_ROOT) / "infra"
TOOL_TIMEOUT = 120

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class ToolResult(dict):
    pass


def _tool(name: str, status: str, reason: str | None = None, findings: int = 0, duration: int = 0) -> dict:
    return {
        "tool": name,
        "status": status,
        "reason": reason,
        "findings": findings,
        "duration_ms": duration,
    }


def _run(cmd: list[str], cwd: Path, timeout: int = TOOL_TIMEOUT) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------- findings
def _finding_key(scan_source: str, rule_id: str, resource: str) -> str:
    raw = f"{scan_source}|{rule_id}|{resource}".lower()
    return re.sub(r"\s+", "-", raw)[:190]


def _upsert(
    db: Session,
    *,
    scan_id: str,
    items: list[dict[str, Any]],
    seen: set[str],
) -> tuple[int, int]:
    created = updated = 0
    now = utcnow()
    for item in items:
        key = item["finding_key"]
        seen.add(key)
        existing = db.query(SecurityFinding).filter(SecurityFinding.finding_key == key).first()
        if existing:
            existing.last_seen_at = now
            existing.severity = item["severity"]
            existing.evidence = item["evidence"]
            existing.scan_id = scan_id
            if existing.status == "resolved":
                existing.status = "open"
            updated += 1
        else:
            db.add(
                SecurityFinding(
                    scan_id=scan_id,
                    scan_source=item["scan_source"],
                    source_kind=item["source_kind"],
                    status="open",
                    first_seen_at=now,
                    last_seen_at=now,
                    **{
                        k: item[k]
                        for k in (
                            "finding_key",
                            "title",
                            "severity",
                            "category",
                            "resource_name",
                            "resource_type",
                            "description",
                            "evidence",
                            "remediation",
                        )
                    },
                )
            )
            created += 1
    db.flush()
    return created, updated


# ---------------------------------------------------------- AWS config audit
def scan_aws_config(db: Session) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status = aws_service.connection_status()
    findings: list[dict[str, Any]] = []

    for bucket in aws_service.list_s3():
        name = bucket["name"]
        detail = bucket.get("detail") or {}
        simulated = bucket["source"] == "simulated"
        pab = detail.get("public_access_block") or {}
        blocked = all(
            pab.get(key) for key in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
        ) if pab else False
        if not blocked:
            findings.append(
                {
                    "finding_key": _finding_key("aws-s3", "s3-public-access-block", name),
                    "title": "S3 bucket does not block all public access",
                    "severity": "high",
                    "category": "s3",
                    "resource_name": name,
                    "resource_type": "s3-bucket",
                    "description": (
                        "Public access block is not fully enabled, so an ACL or bucket policy "
                        "could expose objects publicly."
                        + (" Derived from the simulated inventory." if simulated else "")
                    ),
                    "evidence": json.dumps(pab or {"public_access_block": "not configured"}),
                    "remediation": "Enable all four S3 Block Public Access settings on the bucket and review bucket policies.",
                    "scan_source": "aws-config-audit",
                    "source_kind": "simulated" if simulated else "aws",
                }
            )
        if detail.get("public_acl"):
            findings.append(
                {
                    "finding_key": _finding_key("aws-s3", "s3-public-acl", name),
                    "title": "S3 bucket ACL grants public access",
                    "severity": "critical",
                    "category": "s3",
                    "resource_name": name,
                    "resource_type": "s3-bucket",
                    "description": (
                        "The bucket ACL contains an AllUsers grant, which exposes objects to the internet."
                        + (" Derived from the simulated inventory." if simulated else "")
                    ),
                    "evidence": json.dumps({"public_acl": True, "grants": "AllUsers"}),
                    "remediation": "Remove public grants, enable Block Public Access, and serve assets through CloudFront with OAC.",
                    "scan_source": "aws-config-audit",
                    "source_kind": "simulated" if simulated else "aws",
                }
            )
        if detail.get("encryption") is False:
            findings.append(
                {
                    "finding_key": _finding_key("aws-s3", "s3-encryption", name),
                    "title": "S3 bucket has no default encryption",
                    "severity": "medium",
                    "category": "encryption",
                    "resource_name": name,
                    "resource_type": "s3-bucket",
                    "description": "No server-side encryption configuration was detected on the bucket."
                    + (" Derived from the simulated inventory." if simulated else ""),
                    "evidence": json.dumps({"encryption": False}),
                    "remediation": "Enable SSE-S3 or SSE-KMS default encryption on the bucket.",
                    "scan_source": "aws-config-audit",
                    "source_kind": "simulated" if simulated else "aws",
                }
            )

    for group in aws_service.list_security_groups():
        detail = group.get("detail") or {}
        simulated = group["source"] == "simulated"
        for rule in detail.get("ingress", []):
            cidrs = [c for c in rule.get("cidrs", []) if c]
            if not any(c in aws_service.PUBLIC_CIDRS for c in cidrs):
                continue
            from_port = rule.get("from_port")
            to_port = rule.get("to_port")
            protocol = rule.get("protocol")
            if protocol == "-1" or (from_port in (None, 0) and to_port in (None, 0)):
                findings.append(
                    {
                        "finding_key": _finding_key("aws-sg", "sg-all-traffic", group["resource_id"]),
                        "title": "Security group allows all traffic from the internet",
                        "severity": "critical",
                        "category": "network",
                        "resource_name": group["name"],
                        "resource_type": "security-group",
                        "description": "Ingress rule permits every protocol and port from 0.0.0.0/0."
                        + (" Derived from the simulated inventory." if simulated else ""),
                        "evidence": json.dumps(rule),
                        "remediation": "Restrict the rule to trusted CIDR ranges and specific ports.",
                        "scan_source": "aws-config-audit",
                        "source_kind": "simulated" if simulated else "aws",
                    }
                )
                continue
            exposed = {
                port: label
                for port, label in aws_service.SENSITIVE_PORTS.items()
                if from_port is not None and to_port is not None and int(from_port) <= port <= int(to_port)
            }
            for port, label in exposed.items():
                findings.append(
                    {
                        "finding_key": _finding_key("aws-sg", f"sg-open-{port}", group["resource_id"]),
                        "title": f"{label} ({port}) exposed to the internet",
                        "severity": "critical" if port in (22, 3389) else "high",
                        "category": "network",
                        "resource_name": group["name"],
                        "resource_type": "security-group",
                        "description": (
                            f"Ingress allows {label} port {port} from 0.0.0.0/0."
                            + (" Derived from the simulated inventory." if simulated else "")
                        ),
                        "evidence": json.dumps(rule),
                        "remediation": (
                            f"Remove the 0.0.0.0/0 rule for port {port}; use a bastion, VPN or SSM Session Manager. "
                            "Reference: AWS Well-Architected SEC05-BP03."
                        ),
                        "scan_source": "aws-config-audit",
                        "source_kind": "simulated" if simulated else "aws",
                    }
                )

    for policy in aws_service.list_iam_risks():
        detail = policy.get("detail") or {}
        simulated = policy["source"] == "simulated"
        issues = detail.get("issues") or []
        if not issues:
            continue
        severity = "critical" if any("full administrator" in issue for issue in issues) else "high"
        findings.append(
            {
                "finding_key": _finding_key("aws-iam", "iam-wildcard", policy["resource_id"]),
                "title": "Over-privileged IAM policy",
                "severity": severity,
                "category": "iam",
                "resource_name": policy["name"],
                "resource_type": "iam-policy",
                "description": "; ".join(issues)
                + (" Derived from the simulated inventory." if simulated else ""),
                "evidence": json.dumps(detail),
                "remediation": "Apply least privilege: scope actions and resources, remove wildcards, and review with IAM Access Analyzer.",
                "scan_source": "aws-config-audit",
                "source_kind": "simulated" if simulated else "aws",
            }
        )

    return findings, {
        "aws_mode": status["mode"],
        "connected": status["connected"],
        "simulated": status["mode"] != "connected",
    }


# ------------------------------------------------------- built-in policy rules
def _is_egress_rule(content: str, index: int) -> bool:
    """True when the matched 0.0.0.0/0 belongs to an egress/route block.

    Outbound 0.0.0.0/0 is normal and must not be reported as an exposure;
    only inbound rules are findings.
    """
    window = content[max(0, index - 800) : index]
    positions = [
        (window.rfind("egress"), "egress"),
        (window.rfind("ingress"), "ingress"),
        (window.rfind("route {"), "route"),
    ]
    present = [(pos, kind) for pos, kind in positions if pos >= 0]
    if not present:
        return False
    _, nearest = max(present)
    return nearest in {"egress", "route"}


def scan_repository_rules() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    scanned_files: list[str] = []
    tf_files = sorted(INFRA_DIR.rglob("*.tf")) if INFRA_DIR.exists() else []
    for path in tf_files:
        scanned_files.append(str(path.relative_to(REPO_ROOT)))
        content = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        checks = [
            (
                r'acl\s*=\s*"public-read(-write)?"',
                "public-acl",
                "S3 bucket ACL is public",
                "critical",
                "s3",
                'Remove the public ACL and enable aws_s3_bucket_public_access_block.',
            ),
            (
                r'cidr_blocks\s*=\s*\[\s*"0\.0\.0\.0/0"\s*\]',
                "open-cidr",
                "Security group allows 0.0.0.0/0",
                "high",
                "network",
                "Restrict ingress to trusted CIDRs or front the service with a load balancer.",
            ),
            (
                r"encrypted\s*=\s*false",
                "unencrypted",
                "Resource explicitly disables encryption",
                "high",
                "encryption",
                "Set encrypted = true and use a customer managed KMS key where required.",
            ),
            (
                r'sid\s*=\s*"\*"',
                "iam-wildcard",
                "IAM policy statement uses wildcard action",
                "high",
                "iam",
                "Replace '*' with the minimum required actions and resources.",
            ),
        ]
        for pattern, rule_id, title, severity, category, remediation in checks:
            for match in re.finditer(pattern, content):
                if rule_id == "open-cidr" and _is_egress_rule(content, match.start()):
                    continue
                line = content[: match.start()].count("\n") + 1
                findings.append(
                    {
                        "finding_key": _finding_key("iac-rules", rule_id, f"{rel}:{line}"),
                        "title": title,
                        "severity": severity,
                        "category": category,
                        "resource_name": rel,
                        "resource_type": "terraform",
                        "description": f"{title} detected in {rel} at line {line}.",
                        "evidence": match.group(0),
                        "remediation": remediation,
                        "scan_source": "sentinel-iac-rules",
                        "source_kind": "rule-engine",
                    }
                )

    dockerfiles = [p for p in Path(REPO_ROOT).rglob("Dockerfile*") if ".venv" not in str(p) and "node_modules" not in str(p)]
    for path in dockerfiles:
        scanned_files.append(str(path.relative_to(REPO_ROOT)))
        content = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        if re.search(r"^FROM\s+\S+:latest", content, re.MULTILINE):
            findings.append(
                {
                    "finding_key": _finding_key("iac-rules", "docker-latest-tag", rel),
                    "title": "Dockerfile uses the mutable ':latest' tag",
                    "severity": "medium",
                    "category": "container",
                    "resource_name": rel,
                    "resource_type": "dockerfile",
                    "description": "Base images must be pinned to an immutable tag or digest for reproducible builds.",
                    "evidence": "FROM ...:latest",
                    "remediation": "Pin the base image by version or digest.",
                    "scan_source": "sentinel-iac-rules",
                    "source_kind": "rule-engine",
                }
            )
        if re.search(r"^USER\s+root\s*$", content, re.MULTILINE) or not re.search(r"^USER\s+", content, re.MULTILINE):
            findings.append(
                {
                    "finding_key": _finding_key("iac-rules", "docker-root-user", rel),
                    "title": "Container image runs as root",
                    "severity": "medium",
                    "category": "container",
                    "resource_name": rel,
                    "resource_type": "dockerfile",
                    "description": "No non-root USER instruction was found in the Dockerfile.",
                    "evidence": "missing USER directive",
                    "remediation": "Create an unprivileged user and switch with the USER instruction.",
                    "scan_source": "sentinel-iac-rules",
                    "source_kind": "rule-engine",
                }
            )
    return findings, {"files_scanned": len(scanned_files), "paths": scanned_files[:50]}


# ------------------------------------------------------------- bandit
def run_bandit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.time()
    if shutil.which("bandit") is None and not _module_available("bandit"):
        return [], _tool("bandit", "skipped", "bandit is not installed in this environment", 0, 0)
    target = BACKEND_DIR / "app"
    if not target.exists():
        return [], _tool("bandit", "skipped", "backend/app not found", 0, 0)
    cmd = [sys.executable, "-m", "bandit", "-r", str(target), "-f", "json", "-ll", "-x", "tests"]
    try:
        code, stdout, stderr = _run(cmd, Path(REPO_ROOT))
    except subprocess.TimeoutExpired:
        return [], _tool("bandit", "failed", "bandit timed out", 0, int((time.time() - started) * 1000))
    duration = int((time.time() - started) * 1000)
    if not stdout.strip():
        return [], _tool("bandit", "failed", (stderr or "no output")[:400], 0, duration)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return [], _tool("bandit", "failed", "bandit produced unparsable output", 0, duration)

    severity_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    findings = []
    for result in data.get("results", []):
        path = str(result.get("filename", "")).replace("\\", "/")
        try:
            path = str(Path(path).relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            pass
        line = result.get("line_number", 0)
        findings.append(
            {
                "finding_key": _finding_key("bandit", result.get("test_id", "B000"), f"{path}:{line}"),
                "title": result.get("test_name", "Bandit finding").replace("_", " ").capitalize(),
                "severity": severity_map.get(result.get("issue_severity", "LOW"), "low"),
                "category": "code",
                "resource_name": f"{path}:{line}",
                "resource_type": "python-source",
                "description": (result.get("issue_text") or "")[:900],
                "evidence": (result.get("code") or "").strip()[:900],
                "remediation": (result.get("more_info") or "Review the flagged code path and remove the risky pattern.")[:500],
                "scan_source": "bandit",
                "source_kind": "tool",
            }
        )
    status = _tool("bandit", "executed", None, len(findings), duration)
    status["metrics"] = data.get("metrics", {})
    return findings, status


# ------------------------------------------------------------ pip-audit
def run_pip_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.time()
    if not _module_available("pip_audit"):
        return [], _tool("pip-audit", "skipped", "pip-audit is not installed in this environment", 0, 0)
    req = BACKEND_DIR / "requirements.txt"
    if not req.exists():
        return [], _tool("pip-audit", "skipped", "backend/requirements.txt not found", 0, 0)
    cmd = [sys.executable, "-m", "pip_audit", "-r", str(req), "-f", "json", "--progress-spinner", "off"]
    try:
        code, stdout, stderr = _run(cmd, Path(REPO_ROOT), timeout=180)
    except subprocess.TimeoutExpired:
        return [], _tool("pip-audit", "failed", "pip-audit timed out (offline?)", 0, int((time.time() - started) * 1000))
    duration = int((time.time() - started) * 1000)
    if not stdout.strip():
        return [], _tool("pip-audit", "failed", (stderr or "no output")[:400], 0, duration)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return [], _tool("pip-audit", "failed", "pip-audit produced unparsable output", 0, duration)

    dependencies = data.get("dependencies", data if isinstance(data, list) else [])
    findings = []
    for dep in dependencies:
        for vuln in dep.get("vulns", []) or []:
            vuln_id = vuln.get("id", "unknown")
            fixes = ", ".join(vuln.get("fix_versions", []) or []) or "no fixed version published"
            findings.append(
                {
                    "finding_key": _finding_key("pip-audit", vuln_id, dep.get("name", "")),
                    "title": f"Vulnerable dependency: {dep.get('name')} {dep.get('version')}",
                    "severity": "high",
                    "category": "dependencies",
                    "resource_name": f"{dep.get('name')}=={dep.get('version')}",
                    "resource_type": "python-package",
                    "description": (vuln.get("description") or f"Advisory {vuln_id} affects this package.")[:900],
                    "evidence": json.dumps(
                        {"id": vuln_id, "aliases": vuln.get("aliases", []), "fix_versions": vuln.get("fix_versions", [])}
                    ),
                    "remediation": f"Upgrade {dep.get('name')} to a fixed version: {fixes}.",
                    "scan_source": "pip-audit",
                    "source_kind": "tool",
                }
            )
    return findings, _tool("pip-audit", "executed", None, len(findings), duration)


# -------------------------------------------------------------- checkov
def run_checkov() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.time()
    if not _module_available("checkov") and shutil.which("checkov") is None:
        return [], _tool("checkov", "skipped", "checkov is not installed in this environment", 0, 0)
    if not INFRA_DIR.exists():
        return [], _tool("checkov", "skipped", "infra/terraform not found", 0, 0)
    cmd = [sys.executable, "-m", "checkov.main", "-d", str(INFRA_DIR), "-o", "json", "--quiet", "--compact"]
    try:
        code, stdout, stderr = _run(cmd, Path(REPO_ROOT), timeout=180)
    except subprocess.TimeoutExpired:
        return [], _tool("checkov", "failed", "checkov timed out", 0, int((time.time() - started) * 1000))
    duration = int((time.time() - started) * 1000)
    if not stdout.strip():
        return [], _tool("checkov", "failed", (stderr or "no output")[:400], 0, duration)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return [], _tool("checkov", "failed", "checkov produced unparsable output", 0, duration)
    reports = data if isinstance(data, list) else [data]
    findings = []
    for report in reports:
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        for check in summary.get("failed_checks", []) or []:
            resource = str(check.get("resource", ""))
            sev = (check.get("severity") or "MEDIUM").lower()
            if sev not in SEVERITY_ORDER:
                sev = "medium"
            findings.append(
                {
                    "finding_key": _finding_key("checkov", check.get("check_id", "CKV"), resource),
                    "title": check.get("check_name", "Terraform misconfiguration"),
                    "severity": sev,
                    "category": check.get("check_type", "terraform"),
                    "resource_name": resource,
                    "resource_type": "terraform",
                    "description": check.get("check_name", ""),
                    "evidence": json.dumps({"file": check.get("file_path"), "lines": check.get("file_line_range")}),
                    "remediation": check.get("guideline") or "Apply the Checkov remediation guidance for this check.",
                    "scan_source": "checkov",
                    "source_kind": "tool",
                }
            )
    return findings, _tool("checkov", "executed", None, len(findings), duration)


# ---------------------------------------------------------------- trivy
def run_trivy() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.time()
    binary = shutil.which("trivy")
    if not binary:
        return [], _tool("trivy", "skipped", "trivy binary is not installed in this environment", 0, 0)
    cmd = [binary, "fs", "--format", "json", "--quiet", "--scanners", "vuln,misconfig", str(REPO_ROOT)]
    try:
        code, stdout, stderr = _run(cmd, Path(REPO_ROOT), timeout=240)
    except subprocess.TimeoutExpired:
        return [], _tool("trivy", "failed", "trivy timed out", 0, int((time.time() - started) * 1000))
    duration = int((time.time() - started) * 1000)
    if not stdout.strip():
        return [], _tool("trivy", "failed", (stderr or "no output")[:400], 0, duration)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return [], _tool("trivy", "failed", "trivy produced unparsable output", 0, duration)
    findings = []
    for result in data.get("Results", []) or []:
        target = result.get("Target", "")
        for vuln in result.get("Vulnerabilities", []) or []:
            findings.append(
                {
                    "finding_key": _finding_key("trivy", vuln.get("VulnerabilityID", "VULN"), f"{target}:{vuln.get('PkgName')}"),
                    "title": f"{vuln.get('PkgName')}: {vuln.get('Title') or vuln.get('VulnerabilityID')}",
                    "severity": (vuln.get("Severity") or "MEDIUM").lower(),
                    "category": "container",
                    "resource_name": target,
                    "resource_type": "container-image",
                    "description": vuln.get("Description", "")[:900],
                    "evidence": json.dumps(
                        {
                            "package": vuln.get("PkgName"),
                            "installed": vuln.get("InstalledVersion"),
                            "fixed": vuln.get("FixedVersion"),
                        }
                    ),
                    "remediation": f"Upgrade to {vuln.get('FixedVersion') or 'a patched base image'}.",
                    "scan_source": "trivy",
                    "source_kind": "tool",
                }
            )
        for misconfig in result.get("Misconfigurations", []) or []:
            findings.append(
                {
                    "finding_key": _finding_key("trivy", misconfig.get("ID", "MISC"), target),
                    "title": misconfig.get("Title", "Misconfiguration"),
                    "severity": (misconfig.get("Severity") or "MEDIUM").lower(),
                    "category": "iac",
                    "resource_name": target,
                    "resource_type": "configuration",
                    "description": misconfig.get("Description", "")[:900],
                    "evidence": misconfig.get("Message", "")[:500],
                    "remediation": misconfig.get("Resolution", "Apply the recommended configuration.")[:500],
                    "scan_source": "trivy",
                    "source_kind": "tool",
                }
            )
    return findings, _tool("trivy", "executed", None, len(findings), duration)


def _module_available(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


# ------------------------------------------------------------ orchestration
TOOL_RUNNERS: dict[str, Callable[[], tuple[list[dict[str, Any]], dict[str, Any]]]] = {
    "bandit": run_bandit,
    "pip-audit": run_pip_audit,
    "checkov": run_checkov,
    "trivy": run_trivy,
}

ALL_TOOLS = ["rules", "aws", "bandit", "pip-audit", "checkov", "trivy"]
FAST_TOOLS = ["rules", "aws", "bandit"]


def run_scan(
    db: Session,
    *,
    tools: list[str] | None = None,
    include_cloud: bool = True,
    actor: str = "system",
    scan_id: str | None = None,
) -> dict[str, Any]:
    scan_id = scan_id or uuid.uuid4().hex[:16]
    started = utcnow()
    requested = [t.lower() for t in (tools or FAST_TOOLS)]
    if not include_cloud and "aws" in requested:
        requested.remove("aws")

    all_findings: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}

    if "rules" in requested:
        items, info = scan_repository_rules()
        all_findings.extend(items)
        meta["repository_rules"] = info
        tool_results.append(
            _tool("sentinel-iac-rules", "executed", None, len(items), 0)
        )

    if "aws" in requested:
        items, info = scan_aws_config(db)
        all_findings.extend(items)
        meta["aws"] = info
        tool_results.append(
            _tool(
                "aws-config-audit",
                "executed",
                "simulated inventory used" if info["simulated"] else None,
                len(items),
                0,
            )
        )
        meta["simulated_resources"] = info["simulated"]
        meta["aws_connected"] = info["connected"]

    for tool in requested:
        if tool in {"rules", "aws"}:
            continue
        runner = TOOL_RUNNERS.get(tool)
        if not runner:
            tool_results.append(_tool(tool, "skipped", "unknown tool"))
            continue
        try:
            items, status = runner()
        except Exception as exc:  # pragma: no cover - tool isolation
            logger.exception("scanner %s crashed", tool)
            items, status = [], _tool(tool, "failed", str(exc)[:300])
        all_findings.extend(items)
        tool_results.append(status)

    seen: set[str] = set()
    created, updated = _upsert(db, scan_id=scan_id, items=all_findings, seen=seen)
    db.commit()

    # close findings from the same sources that no longer reproduce
    resolved = 0
    sources = {item["scan_source"] for item in all_findings}
    if sources:
        stale = (
            db.query(SecurityFinding)
            .filter(SecurityFinding.status == "open", SecurityFinding.scan_source.in_(sources))
            .all()
        )
        for finding in stale:
            if finding.finding_key not in seen:
                finding.status = "resolved"
                finding.last_seen_at = utcnow()
                resolved += 1
        db.commit()

    finished = utcnow()
    result = {
        "scan_id": scan_id,
        "started_at": started,
        "finished_at": finished,
        "findings_created": created,
        "findings_updated": updated,
        "findings_resolved": resolved,
        "tools": tool_results,
        "simulated_resources": bool(meta.get("simulated_resources", False)),
        "aws_connected": bool(meta.get("aws_connected", False)),
    }
    record_audit(
        db,
        actor=actor,
        action="security.scan",
        entity_type="security_scan",
        entity_id=scan_id,
        detail={
            "tools": requested,
            "created": created,
            "updated": updated,
            "resolved": resolved,
            "simulated": result["simulated_resources"],
        },
    )
    return result


# --------------------------------------------------------------- reporting
def findings_query(db: Session, **filters):
    query = db.query(SecurityFinding)
    return query


def export_json(db: Session, findings: list[SecurityFinding]) -> str:
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "product": "CloudOps Sentinel",
        "finding_count": len(findings),
        "findings": [
            {
                "finding_id": f.finding_key,
                "title": f.title,
                "severity": f.severity,
                "category": f.category,
                "resource_name": f.resource_name,
                "resource_type": f.resource_type,
                "description": f.description,
                "evidence": f.evidence,
                "remediation": f.remediation,
                "scan_source": f.scan_source,
                "source_kind": f.source_kind,
                "status": f.status,
                "scan_timestamp": f.last_seen_at.isoformat() + "Z",
                "first_seen": f.first_seen_at.isoformat() + "Z",
            }
            for f in findings
        ],
    }
    return json.dumps(payload, indent=2)


def export_csv(findings: list[SecurityFinding]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "finding_id",
            "title",
            "severity",
            "category",
            "resource_name",
            "resource_type",
            "description",
            "evidence",
            "remediation",
            "scan_source",
            "source_kind",
            "status",
            "scan_timestamp",
        ]
    )
    for f in findings:
        writer.writerow(
            [
                f.finding_key,
                f.title,
                f.severity,
                f.category,
                f.resource_name,
                f.resource_type,
                f.description.replace("\n", " "),
                f.evidence.replace("\n", " ")[:500],
                f.remediation.replace("\n", " "),
                f.scan_source,
                f.source_kind,
                f.status,
                f.last_seen_at.isoformat() + "Z",
            ]
        )
    return buffer.getvalue()


def severity_summary(db: Session) -> dict[str, Any]:
    rows = db.query(SecurityFinding).filter(SecurityFinding.status == "open").all()
    counts = {key: 0 for key in SEVERITY_ORDER}
    for row in rows:
        counts[row.severity] = counts.get(row.severity, 0) + 1
    weighted = counts["critical"] * 10 + counts["high"] * 5 + counts["medium"] * 2 + counts["low"]
    score = min(100, weighted)
    return {
        "counts": counts,
        "total": len(rows),
        "risk_score": score,
        "risk_level": "critical" if score >= 60 else "high" if score >= 35 else "medium" if score >= 15 else "low",
        "by_source_kind": {
            kind: sum(1 for row in rows if row.source_kind == kind)
            for kind in {row.source_kind for row in rows}
        },
    }
