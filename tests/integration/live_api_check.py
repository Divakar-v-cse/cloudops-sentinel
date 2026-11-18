#!/usr/bin/env python3
"""End-to-end API check against a running CloudOps Sentinel instance.

Unlike the pytest suite (which builds its own temporary database), this script
exercises a live server, including the scheduler-backed endpoints and the
security scanner subprocesses. It is read/write against the target database:
it creates one incident and two remediation actions (a dry-run and a pending
approval). Point it at a development instance.

Usage:
    python tests/integration/live_api_check.py
    python tests/integration/live_api_check.py --base-url http://127.0.0.1:8010 \
        --email admin@cloudops.local --password 'Admin@12345'
"""
from __future__ import annotations

import argparse
import sys

import httpx

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append((name, detail))
    status = "PASS" if condition else "FAIL"
    print(f"{status}  {name}" + (f"  :: {detail[:200]}" if detail and not condition else ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--email", default="admin@cloudops.local")
    parser.add_argument("--password", default="Admin@12345")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=180)

    health = client.get("/health")
    check("health is up", health.status_code == 200 and health.json().get("database") == "ok", health.text)

    login = client.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
    check("login", login.status_code == 200, login.text)
    if login.status_code != 200:
        return 1
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    overview = client.get("/api/v1/dashboard/overview", headers=headers)
    body = overview.json() if overview.status_code == 200 else {}
    check("dashboard totals", overview.status_code == 200 and body.get("instances", {}).get("total", 0) >= 8, str(body)[:200])
    check("dashboard labels simulated data", body.get("mode", {}).get("data_sources", {}).get("simulated", 0) >= 1)

    instances = client.get("/api/v1/instances", headers=headers)
    rows = instances.json() if instances.status_code == 200 else []
    check("inventory lists instances", instances.status_code == 200 and len(rows) >= 8, instances.text[:200])
    simulated = next((row for row in rows if row["source"] == "simulated"), None)
    local = next((row for row in rows if row["source"] == "local"), None)
    check("local host is registered", local is not None)
    if simulated:
        detail = client.get(f"/api/v1/instances/{simulated['id']}", headers=headers)
        check("instance detail has a metric", detail.status_code == 200 and detail.json()["latest_metric"] is not None)
        history = client.get(f"/api/v1/instances/{simulated['id']}/metrics?hours=6", headers=headers)
        check("metric history exists", history.status_code == 200 and len(history.json()) > 5)

    check("alerts endpoint", client.get("/api/v1/monitoring/alerts", headers=headers).status_code == 200)

    scan = client.post(
        "/api/v1/security/scan",
        headers=headers,
        json={"tools": ["rules", "aws", "bandit"], "include_cloud": True},
    )
    scan_body = scan.json() if scan.status_code == 200 else {}
    check("security scan runs", scan.status_code == 200 and bool(scan_body.get("scan_id")), scan.text[:300])
    statuses = {tool["tool"]: tool["status"] for tool in scan_body.get("tools", [])}
    check("scan reports tool outcomes", "bandit" in statuses and statuses["bandit"] in {"executed", "skipped", "failed"})

    findings = client.get("/api/v1/security/findings?status=open&page_size=50", headers=headers)
    finding_body = findings.json() if findings.status_code == 200 else {}
    check("findings are listed", findings.status_code == 200 and finding_body.get("total", 0) > 0)
    simulated_findings = [f for f in finding_body.get("items", []) if f["source_kind"] == "simulated"]
    check(
        "simulated findings say so",
        all("simulated" in f["description"].lower() for f in simulated_findings),
        str(simulated_findings[:1])[:200],
    )

    report = client.get("/api/v1/security/report?format=csv", headers=headers)
    check("csv report downloads", report.status_code == 200 and report.text.startswith("finding_id"))

    cost = client.get("/api/v1/costs/summary", headers=headers)
    check("cost is labelled estimated", cost.status_code == 200 and cost.json().get("source") == "estimated")

    groups = client.get("/api/v1/logs/groups?hours=720", headers=headers)
    check("log groups exist", groups.status_code == 200 and len(groups.json()) > 0)

    analysis = client.post("/api/v1/logs/analyze", headers=headers, json={"hours": 24})
    analysis_body = analysis.json() if analysis.status_code == 200 else {}
    check(
        "analysis discloses its source and uncertainty",
        analysis.status_code == 200
        and analysis_body.get("source") in {"ai", "rule-based"}
        and "not a confirmed root cause" in analysis_body.get("disclaimer", "").lower(),
        str(analysis_body)[:200],
    )

    created = client.post(
        "/api/v1/incidents",
        headers=headers,
        json={"title": "Live API check incident", "severity": "low", "description": "created by live_api_check.py"},
    )
    check("incident creation", created.status_code == 201, created.text[:200])
    if created.status_code == 201:
        incident = created.json()
        illegal = client.post(f"/api/v1/incidents/{incident['id']}/status", headers=headers, json={"status": "closed"})
        check("illegal transition rejected", illegal.status_code == 409, str(illegal.status_code))
        ack = client.post(
            f"/api/v1/incidents/{incident['id']}/status",
            headers=headers,
            json={"status": "acknowledged", "note": "acknowledged by live check"},
        )
        check("acknowledgement accepted", ack.status_code == 200, ack.text[:150])

    catalog = client.get("/api/v1/remediation/catalog", headers=headers).json()
    names = {item["name"] for item in catalog}
    check("catalog is allowlisted", "restart_service" in names and "terminate_instance" not in names)
    check("no destructive action exposed", all(not item["destructive"] for item in catalog))

    if simulated:
        dry = client.post(
            "/api/v1/remediation/actions",
            headers=headers,
            json={"action_name": "restart_service", "instance_id": simulated["id"], "dry_run": True},
        )
        dry_body = dry.json() if dry.status_code == 201 else {}
        check(
            "dry-run makes no change",
            dry.status_code == 201 and dry_body.get("status") == "dry_run" and "No change was made" in (dry_body.get("output") or ""),
            str(dry_body)[:250],
        )

        real = client.post(
            "/api/v1/remediation/actions",
            headers=headers,
            json={"action_name": "restart_service", "instance_id": simulated["id"], "dry_run": False},
        )
        real_body = real.json() if real.status_code == 201 else {}
        check("real action waits for approval", real.status_code == 201 and real_body.get("status") == "pending_approval")
        if real_body.get("id"):
            early = client.post(f"/api/v1/remediation/actions/{real_body['id']}/execute", headers=headers)
            check("execution blocked before approval", early.status_code == 409, str(early.status_code))
            self_approve = client.post(f"/api/v1/remediation/actions/{real_body['id']}/approve", headers=headers, json={})
            check("requester cannot self-approve", self_approve.status_code == 403, str(self_approve.status_code))

    forbidden = client.post(
        "/api/v1/remediation/actions",
        headers=headers,
        json={"action_name": "terminate_instance", "instance_id": simulated["id"] if simulated else 1, "dry_run": True},
    )
    check("destructive action rejected", forbidden.status_code == 422, str(forbidden.status_code))

    pipelines = client.get("/api/v1/pipelines", headers=headers)
    pipeline_rows = pipelines.json() if pipelines.status_code == 200 else []
    check("pipelines discovered", pipelines.status_code == 200 and len(pipeline_rows) >= 3)
    check("repository CI config detected", any(row["detected"] for row in pipeline_rows))

    aws_status = client.get("/api/v1/aws/status", headers=headers)
    check("aws status is explicit", aws_status.status_code == 200 and "mode" in aws_status.json())

    audit = client.get("/api/v1/audit?page_size=100", headers=headers)
    actions = {entry["action"] for entry in audit.json()["items"]} if audit.status_code == 200 else set()
    check("audit trail records login and scan", "auth.login" in actions and "security.scan" in actions, str(sorted(actions))[:200])

    runtime = client.get("/api/v1/settings/runtime", headers=headers)
    runtime_body = runtime.json() if runtime.status_code == 200 else {}
    check("runtime hides secrets", runtime.status_code == 200 and "secret_key" not in {k.lower() for k in runtime_body})

    metrics = client.get("/metrics")
    check("prometheus metrics", metrics.status_code == 200 and "sentinel_instances_total" in metrics.text)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name, detail in FAIL:
        print(f"  - {name}: {detail[:300]}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
