"""Log ingestion, grouping and analysis.

Analysis has two paths:
1. ``ai`` - only used when an OpenAI-compatible endpoint is explicitly
   configured (AI_PROVIDER + AI_API_KEY). The response is parsed strictly and
   any failure falls back to path 2.
2. ``rule-based`` - deterministic pattern matching over the actual log lines.
   It always works, needs no key, and never claims a confirmed root cause.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.utils import utcnow
from app.models import ApplicationLog, Incident, InfrastructureInstance

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Hypotheses are generated from log patterns and are not a confirmed root cause. "
    "Validate each step against live telemetry before changing production."
)

_NORMALISERS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hex>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"), "<ts>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|kb|mb|gb|kbps|%)?\b", re.I), "<n>"),
    (re.compile(r"\b(pid|port|connection|conn|id|request|trace)[=: ]+[\w-]+", re.I), r"\1=<id>"),
    (re.compile(r"\s+"), " "),
]

_LEVEL_SEVERITY = {
    "CRITICAL": "critical",
    "FATAL": "critical",
    "PANIC": "critical",
    "ERROR": "error",
    "ERR": "error",
    "WARN": "warning",
    "WARNING": "warning",
    "NOTICE": "info",
    "INFO": "info",
    "DEBUG": "info",
    "TRACE": "info",
}

_CRITICAL_HINTS = ("oomkilled", "out of memory", "segmentation fault", "kernel panic", "panic:", "fatal")


def normalise_message(message: str) -> str:
    result = message.lower()
    for pattern, replacement in _NORMALISERS:
        result = pattern.sub(replacement, result)
    return result.strip()[:400]


def fingerprint(service: str, message: str) -> str:
    # SHA-1 is used only as a stable grouping key for log lines, never for
    # authentication or integrity, hence usedforsecurity=False.
    return hashlib.sha1(
        f"{service}:{normalise_message(message)}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:16]


def classify(level: str | None, message: str) -> tuple[str, str]:
    normalised_level = (level or "").upper().strip()
    severity = _LEVEL_SEVERITY.get(normalised_level, "info")
    lowered = message.lower()
    if any(hint in lowered for hint in _CRITICAL_HINTS):
        severity = "critical"
        normalised_level = normalised_level or "CRITICAL"
    elif "error" in lowered and severity == "info":
        severity = "error"
        normalised_level = "ERROR"
    elif ("warn" in lowered or "deprecat" in lowered) and severity == "info":
        severity = "warning"
        normalised_level = "WARN"
    return (normalised_level or "INFO")[:20], severity


def ingest(db: Session, items: list[dict[str, Any]]) -> dict[str, Any]:
    created: list[ApplicationLog] = []
    services: set[str] = set()
    severity_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
    instance_names = {
        row.name.lower(): row.id for row in db.query(InfrastructureInstance).all()
    }
    for item in items:
        level, severity = classify(item.get("level"), item["message"])
        ts = item.get("timestamp") or utcnow()
        if isinstance(ts, str):
            try:
                from datetime import datetime

                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                ts = utcnow()
        instance_id = item.get("instance_id")
        if instance_id is None and item.get("instance"):
            instance_id = instance_names.get(str(item["instance"]).lower())
        row = ApplicationLog(
            service=item["service"][:80],
            level=level,
            severity=severity,
            message=item["message"][:8000],
            timestamp=ts,
            fingerprint=fingerprint(item["service"], item["message"]),
            instance_id=instance_id,
            trace_id=(item.get("trace_id") or None),
            log_metadata=item.get("metadata") or {},
        )
        db.add(row)
        created.append(row)
        services.add(row.service)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    db.commit()
    return {
        "ingested": len(created),
        "services": sorted(services),
        "severity_counts": severity_counts,
        "first_id": created[0].id if created else None,
        "last_id": created[-1].id if created else None,
    }


def search(
    db: Session,
    *,
    query: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    level: str | None = None,
    hours: int | None = None,
    start: Any = None,
    end: Any = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ApplicationLog], int]:
    q = db.query(ApplicationLog)
    if query:
        like = f"%{query}%"
        q = q.filter(or_(ApplicationLog.message.ilike(like), ApplicationLog.trace_id.ilike(like)))
    if service:
        q = q.filter(ApplicationLog.service == service)
    if severity:
        q = q.filter(ApplicationLog.severity == severity)
    if level:
        q = q.filter(ApplicationLog.level == level.upper())
    if hours:
        q = q.filter(ApplicationLog.timestamp >= utcnow() - timedelta(hours=hours))
    if start:
        q = q.filter(ApplicationLog.timestamp >= start)
    if end:
        q = q.filter(ApplicationLog.timestamp <= end)
    total = q.count()
    rows = (
        q.order_by(ApplicationLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def groups(db: Session, *, hours: int = 24, service: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(hours=hours)
    q = (
        db.query(
            ApplicationLog.fingerprint,
            ApplicationLog.service,
            func.count(ApplicationLog.id).label("count"),
            func.min(ApplicationLog.timestamp).label("first_seen"),
            func.max(ApplicationLog.timestamp).label("last_seen"),
            func.max(ApplicationLog.severity).label("severity"),
        )
        .filter(ApplicationLog.timestamp >= since, ApplicationLog.severity.in_(["critical", "error", "warning"]))
        .group_by(ApplicationLog.fingerprint, ApplicationLog.service)
        .order_by(func.count(ApplicationLog.id).desc())
        .limit(limit)
    )
    if service:
        q = q.filter(ApplicationLog.service == service)
    rows = q.all()
    output = []
    severity_rank = {"critical": 3, "error": 2, "warning": 1, "info": 0}
    for row in rows:
        sample = (
            db.query(ApplicationLog)
            .filter(ApplicationLog.fingerprint == row.fingerprint)
            .order_by(ApplicationLog.timestamp.desc())
            .first()
        )
        traces = (
            db.query(func.count(func.distinct(ApplicationLog.trace_id)))
            .filter(ApplicationLog.fingerprint == row.fingerprint, ApplicationLog.trace_id.isnot(None))
            .scalar()
            or 0
        )
        output.append(
            {
                "fingerprint": row.fingerprint,
                "service": row.service,
                "severity": sample.severity if sample else row.severity,
                "sample_message": sample.message[:400] if sample else "",
                "count": row.count,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "affected_traces": traces,
            }
        )
    output.sort(key=lambda item: (severity_rank.get(item["severity"], 0), item["count"]), reverse=True)
    return output


def statistics(db: Session, hours: int = 24) -> dict[str, Any]:
    since = utcnow() - timedelta(hours=hours)
    rows = (
        db.query(ApplicationLog.severity, func.count(ApplicationLog.id))
        .filter(ApplicationLog.timestamp >= since)
        .group_by(ApplicationLog.severity)
        .all()
    )
    by_severity = {sev: count for sev, count in rows}
    services = (
        db.query(ApplicationLog.service, func.count(ApplicationLog.id))
        .filter(ApplicationLog.timestamp >= since)
        .group_by(ApplicationLog.service)
        .order_by(func.count(ApplicationLog.id).desc())
        .limit(10)
        .all()
    )
    timeline = (
        db.query(
            func.strftime("%Y-%m-%d %H:00", ApplicationLog.timestamp).label("bucket")
            if settings.is_sqlite
            else func.date_trunc("hour", ApplicationLog.timestamp).label("bucket"),
            ApplicationLog.severity,
            func.count(ApplicationLog.id),
        )
        .filter(ApplicationLog.timestamp >= since)
        .group_by("bucket", ApplicationLog.severity)
        .order_by("bucket")
        .all()
    )
    return {
        "window_hours": hours,
        "total": sum(by_severity.values()),
        "by_severity": by_severity,
        "top_services": [{"service": s, "count": c} for s, c in services],
        "timeline": [
            {"bucket": str(bucket), "severity": severity, "count": count}
            for bucket, severity, count in timeline
        ],
    }


def retention_cleanup(db: Session, days: int | None = None) -> int:
    days = days or settings.log_retention_days
    cutoff = utcnow() - timedelta(days=days)
    deleted = db.query(ApplicationLog).filter(ApplicationLog.timestamp < cutoff).delete()
    db.commit()
    return deleted


# --------------------------------------------------------------- analysis
def _matching_logs(
    db: Session,
    *,
    log_ids: list[int] | None = None,
    fingerprint_value: str | None = None,
    service: str | None = None,
    hours: int = 24,
    limit: int = 40,
) -> list[ApplicationLog]:
    q = db.query(ApplicationLog)
    if log_ids:
        q = q.filter(ApplicationLog.id.in_(log_ids))
    elif fingerprint_value:
        q = q.filter(ApplicationLog.fingerprint == fingerprint_value)
    else:
        q = q.filter(ApplicationLog.timestamp >= utcnow() - timedelta(hours=hours))
        if service:
            q = q.filter(ApplicationLog.service == service)
        q = q.filter(ApplicationLog.severity.in_(["critical", "error", "warning"]))
    return q.order_by(ApplicationLog.timestamp.desc()).limit(limit).all()


_KNOWLEDGE: list[dict[str, Any]] = [
    {
        "id": "memory-pressure",
        "patterns": ["oomkilled", "out of memory", "memoryerror", "cannot allocate memory", "heap"],
        "summary": "The process or container ran out of available memory.",
        "causes": [
            "Container memory limit is below the application's working set.",
            "A leak or unbounded cache grows until the kernel OOM killer acts.",
            "A traffic spike or large batch job exceeded the provisioned RAM.",
        ],
        "commands": [
            "free -m",
            "ps aux --sort=-%mem | head -n 10",
            "kubectl top pods -n <namespace> --sort-by=memory",
            "kubectl describe pod <pod> -n <namespace> | grep -A3 'Last State'",
            "journalctl -k | grep -i 'out of memory'",
        ],
        "steps": [
            "Confirm whether the kernel or the container runtime killed the process.",
            "Compare the container limit with the observed working set under peak load.",
            "Capture a heap profile before raising limits; a leak will recur.",
        ],
        "confidence": "high",
    },
    {
        "id": "connection-refused",
        "patterns": ["connection refused", "econnrefused", "no route to host", "connect: connection refused"],
        "summary": "A downstream TCP connection was rejected, which usually means nothing is listening.",
        "causes": [
            "The target service is stopped or still starting.",
            "The client points at the wrong host or port.",
            "A security group, network policy or firewall blocks the port.",
        ],
        "commands": [
            "ss -lntp | grep <port>",
            "curl -v http://<host>:<port>/health",
            "systemctl status <service>",
            "kubectl get endpoints <service> -n <namespace>",
            "dig +short <host>",
        ],
        "steps": [
            "Verify the listener exists on the target host.",
            "Check that DNS resolves to the expected address.",
            "Confirm the call path is allowed by security groups and network policies.",
        ],
        "confidence": "high",
    },
    {
        "id": "timeout",
        "patterns": ["timeout", "timed out", "deadline exceeded", "read timeout", "gateway timeout"],
        "summary": "A request exceeded its deadline, indicating latency or a saturated dependency.",
        "causes": [
            "A downstream dependency is slow or overloaded.",
            "Connection pool exhaustion serialises requests.",
            "Network latency or packet loss between services.",
        ],
        "commands": [
            "curl -o /dev/null -s -w '%{time_total}\\n' http://<host>:<port>/health",
            "kubectl logs <pod> --since=15m | grep -i timeout",
            "ss -s",
            "pg_stat_activity query in the database for long-running sessions",
        ],
        "steps": [
            "Find the slowest span for the failing trace.",
            "Check pool saturation metrics for the dependency.",
            "Confirm the configured timeout matches the dependency's p99 latency.",
        ],
        "confidence": "medium",
    },
    {
        "id": "disk-full",
        "patterns": ["no space left on device", "disk full", "enospc", "quota exceeded"],
        "summary": "A filesystem or volume ran out of space.",
        "causes": [
            "Log or container layer growth without rotation.",
            "A volume resize did not propagate to the filesystem.",
            "Large temporary files or database WAL segments accumulate.",
        ],
        "commands": [
            "df -h",
            "du -xh /var --max-depth=2 | sort -h | tail -n 15",
            "docker system df",
            "journalctl --disk-usage",
        ],
        "steps": [
            "Identify the mount that is full and its largest directories.",
            "Purge rotated logs and unused images, then verify free space.",
            "Add retention limits so the condition does not recur.",
        ],
        "confidence": "high",
    },
    {
        "id": "permission-denied",
        "patterns": ["permission denied", "accessdenied", "unauthorized", "forbidden", "not authorized"],
        "summary": "An authorization or filesystem permission check failed.",
        "causes": [
            "The IAM role lacks the required action on the resource.",
            "File or directory ownership changed after a deploy.",
            "An expired or missing token is being presented.",
        ],
        "commands": [
            "id",
            "ls -l <path>",
            "aws sts get-caller-identity",
            "aws iam simulate-principal-policy --policy-source-arn <role-arn> --action-names <action> --resource-arns <resource>",
        ],
        "steps": [
            "Confirm which principal the workload actually uses.",
            "Compare the required action with the attached policy statements.",
            "Prefer scoping the policy over widening file permissions.",
        ],
        "confidence": "medium",
    },
    {
        "id": "upstream-5xx",
        "patterns": ["502", "503", "504", "bad gateway", "service unavailable", "upstream"],
        "summary": "The edge proxy received an invalid or missing response from an upstream.",
        "causes": [
            "No healthy backend registered in the target group.",
            "The application crashed or is restarting.",
            "Health check path or port is misconfigured.",
        ],
        "commands": [
            "kubectl get pods -n <namespace>",
            "kubectl get endpoints <service> -n <namespace>",
            "curl -v http://<pod-ip>:<port>/health",
            "tail -n 100 /var/log/nginx/error.log",
        ],
        "steps": [
            "Confirm the upstream has healthy endpoints.",
            "Check recent restarts and readiness probe failures.",
            "Validate that the health check path returns 200.",
        ],
        "confidence": "medium",
    },
    {
        "id": "db-pool",
        "patterns": ["too many connections", "connection pool", "pool exhausted", "remaining connection slots"],
        "summary": "Database connections are exhausted or the pool is saturated.",
        "causes": [
            "Connections leak because sessions are never returned.",
            "max_connections is below the aggregate pool size of all replicas.",
            "Long-running transactions hold connections.",
        ],
        "commands": [
            "SELECT count(*), state FROM pg_stat_activity GROUP BY state;",
            "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state <> 'idle' ORDER BY duration DESC;",
            "SHOW max_connections;",
        ],
        "steps": [
            "Measure active versus idle connections.",
            "Right-size per-replica pools against max_connections.",
            "Terminate only verified idle-in-transaction sessions.",
        ],
        "confidence": "medium",
    },
    {
        "id": "tls-certificate",
        "patterns": ["certificate", "x509", "ssl error", "tls handshake", "expired"],
        "summary": "A TLS certificate is expired, untrusted or mismatched.",
        "causes": [
            "Automated renewal failed.",
            "The certificate chain is incomplete.",
            "The hostname does not match the certificate SANs.",
        ],
        "commands": [
            "openssl s_client -connect <host>:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -noout -dates -subject",
            "kubectl get certificate -A",
            "certbot certificates",
        ],
        "steps": [
            "Check the expiry and SAN list of the served certificate.",
            "Verify renewal automation and its logs.",
            "Confirm the ingress serves the full chain.",
        ],
        "confidence": "high",
    },
    {
        "id": "deploy-failure",
        "patterns": ["imagepullbackoff", "errimagepull", "crashloopbackoff", "deployment failed", "rollback"],
        "summary": "A deployment could not roll out a healthy revision.",
        "causes": [
            "Image tag or registry credentials are invalid.",
            "The new revision fails readiness probes or crashes on start.",
            "A required environment variable or secret is missing.",
        ],
        "commands": [
            "kubectl rollout status deployment/<name> -n <namespace>",
            "kubectl describe pod <pod> -n <namespace>",
            "kubectl logs <pod> -n <namespace> --previous",
            "kubectl rollout history deployment/<name> -n <namespace>",
        ],
        "steps": [
            "Identify whether the failure is image pull, config or runtime.",
            "Compare the failing revision with the last known good one.",
            "Roll back first to restore service, then debug forward.",
        ],
        "confidence": "medium",
    },
]


def rule_based_analysis(logs: list[ApplicationLog], service: str | None = None) -> dict[str, Any]:
    if not logs:
        return {
            "source": "rule-based",
            "summary": "No matching log lines were found in the selected window.",
            "likely_causes": [],
            "hypotheses": [],
            "debug_commands": [],
            "next_steps": ["Widen the time window or remove filters and retry."],
            "confidence": "low",
            "disclaimer": DISCLAIMER,
        }
    text = " ".join(log.message.lower() for log in logs[:40])
    matched = [entry for entry in _KNOWLEDGE if any(p in text for p in entry["patterns"])]
    severity_counts: dict[str, int] = {}
    for log in logs:
        severity_counts[log.severity] = severity_counts.get(log.severity, 0) + 1
    services = {log.service for log in logs}

    summary_bits = [
        f"{len(logs)} relevant log lines across {len(services)} service(s)"
        + (f" ({', '.join(sorted(services))})" if services else ""),
        "severity mix: " + ", ".join(f"{k}={v}" for k, v in sorted(severity_counts.items())),
    ]
    if matched:
        summary_bits.append("dominant pattern: " + matched[0]["summary"])
    else:
        summary_bits.append(
            "no known failure signature matched; the messages are likely application-specific business errors"
        )

    hypotheses = []
    for entry in matched[:3]:
        evidence = next((log.message[:300] for log in logs if any(p in log.message.lower() for p in entry["patterns"])), "")
        hypotheses.append(
            {
                "id": entry["id"],
                "summary": entry["summary"],
                "confidence": entry["confidence"],
                "evidence": evidence,
                "causes": entry["causes"],
            }
        )
    commands: list[str] = []
    for entry in matched[:3]:
        for command in entry["commands"]:
            if command not in commands:
                commands.append(command)
    steps = [step for entry in matched[:2] for step in entry["steps"]]
    if not steps:
        steps = [
            "Group the errors by fingerprint and compare volume before and after the last deployment.",
            "Correlate the failing trace IDs with upstream and downstream services.",
            "Reproduce with the same request parameters in a non-production environment.",
        ]

    return {
        "source": "rule-based",
        "summary": ". ".join(summary_bits) + ".",
        "likely_causes": [cause for entry in matched[:3] for cause in entry["causes"]][:6],
        "hypotheses": hypotheses,
        "debug_commands": commands[:10],
        "next_steps": steps[:8],
        "confidence": "high" if matched and len(logs) >= 10 else "medium" if matched else "low",
        "disclaimer": DISCLAIMER,
    }


def _ai_analysis(logs: list[ApplicationLog]) -> dict[str, Any] | None:
    if not settings.ai_enabled:
        return None
    sample = [
        {"timestamp": log.timestamp.isoformat(), "service": log.service, "level": log.level, "message": log.message[:500]}
        for log in logs[:30]
    ]
    prompt = (
        "You are an SRE assistant. Analyse these log lines and reply with STRICT JSON only, using keys: "
        'summary (string), likely_causes (array of strings), debug_commands (array of strings), '
        'next_steps (array of strings), confidence ("low"|"medium"|"high"). '
        "Never assert a root cause as confirmed. Logs:\n" + json.dumps(sample)
    )
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(
                f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": "You are a precise SRE log analysis assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
    except Exception as exc:  # noqa: BLE001 - any provider failure must degrade
        logger.warning("AI log analysis unavailable, using rule-based fallback: %s", exc)
        return None

    return {
        "source": "ai",
        "summary": str(data.get("summary", ""))[:2000],
        "likely_causes": [str(c)[:400] for c in data.get("likely_causes", [])][:6],
        "hypotheses": [
            {"id": f"ai-{index}", "summary": str(cause)[:400], "confidence": data.get("confidence", "medium"), "evidence": "", "causes": []}
            for index, cause in enumerate(data.get("likely_causes", [])[:6])
        ],
        "debug_commands": [str(c)[:300] for c in data.get("debug_commands", [])][:10],
        "next_steps": [str(s)[:400] for s in data.get("next_steps", [])][:8],
        "confidence": data.get("confidence", "medium") if data.get("confidence") in {"low", "medium", "high"} else "medium",
        "disclaimer": DISCLAIMER + " This analysis was produced by the configured LLM provider.",
    }


def analyse(
    db: Session,
    *,
    log_ids: list[int] | None = None,
    fingerprint_value: str | None = None,
    service: str | None = None,
    hours: int = 24,
) -> dict[str, Any]:
    logs = _matching_logs(
        db, log_ids=log_ids, fingerprint_value=fingerprint_value, service=service, hours=hours
    )
    result = _ai_analysis(logs) or rule_based_analysis(logs, service)

    related = []
    services = {log.service for log in logs}
    for name in services:
        incidents = (
            db.query(Incident)
            .filter(Incident.service == name, Incident.status.in_(["detected", "acknowledged", "investigating"]))
            .order_by(Incident.created_at.desc())
            .limit(3)
            .all()
        )
        related.extend(
            {
                "id": incident.id,
                "incident_number": incident.incident_number,
                "title": incident.title,
                "severity": incident.severity,
                "status": incident.status,
            }
            for incident in incidents
        )
    result["related_incidents"] = related
    result["log_count"] = len(logs)
    result["services"] = sorted(services)
    return result
