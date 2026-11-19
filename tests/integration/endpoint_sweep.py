"""Endpoint sweep: call every route (including negative cases) and report unexpected codes.

Usage:
    python tests/integration/endpoint_sweep.py --base-url http://127.0.0.1:8000
    python tests/integration/endpoint_sweep.py --base-url http://127.0.0.1:8010 --password '...'

Complements ``live_api_check.py``: that one asserts business behaviour, this one
asserts that no route answers 500 or an unexpected status under odd input.
It writes to the target database, so use a development instance.
"""
from __future__ import annotations

import argparse
import sys

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--email", default="admin@cloudops.local")
parser.add_argument("--password", default="Admin@12345")
args = parser.parse_args()

c = httpx.Client(base_url=args.base_url, timeout=180)
issues: list[str] = []
checked = 0


def call(method: str, path: str, expect=(200, 201), **kwargs):
    global checked
    checked += 1
    try:
        r = c.request(method, path, **kwargs)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"EXC  {method} {path} -> {type(exc).__name__}: {exc}")
        print(f"EXC  {method} {path} {exc}")
        return None
    ok = r.status_code in expect
    if not ok:
        detail = r.text[:220].replace("\n", " ")
        issues.append(f"{r.status_code} {method} {path} -> {detail}")
        print(f"FAIL {r.status_code} {method} {path} :: {detail}")
    else:
        print(f"ok   {r.status_code} {method} {path}")
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text


# ---- public
call("GET", "/health")
call("GET", "/")
call("GET", "/metrics")
call("GET", "/api/v1/dashboard/overview", expect=(401,))

login = c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
if login.status_code != 200:
    print("LOGIN FAILED", login.status_code, login.text)
    sys.exit(1)
H = {"Authorization": f"Bearer {login.json()['access_token']}"}
call("GET", "/api/v1/auth/me", headers=H)
call("GET", "/api/v1/auth/users", headers=H)

# ---- dashboard
ov = call("GET", "/api/v1/dashboard/overview", headers=H) or {}
for key in ("instances", "utilisation", "incidents", "security", "cost", "deployments", "alerts", "trend", "mode"):
    if key not in ov:
        issues.append(f"payload /dashboard/overview missing '{key}'")
call("GET", "/api/v1/dashboard/trend?hours=48", headers=H)
call("GET", "/api/v1/dashboard/trend?hours=0", expect=(422,), headers=H)

# ---- instances
rows = call("GET", "/api/v1/instances", headers=H) or []
sim = next((r for r in rows if r["source"] == "simulated"), None)
loc = next((r for r in rows if r["source"] == "local"), None)
if sim:
    detail = call("GET", f"/api/v1/instances/{sim['id']}", headers=H) or {}
    if not detail.get("latest_metric"):
        issues.append("instance detail has no latest_metric")
    call("GET", f"/api/v1/instances/{sim['id']}/metrics?hours=6", headers=H)
    call("GET", f"/api/v1/instances/{sim['id']}/metrics?hours=999", expect=(422,), headers=H)
    call("PATCH", f"/api/v1/instances/{sim['id']}", headers=H, json={"name": sim["name"]})
    call("POST", f"/api/v1/instances/{sim['id']}/power?action=reboot", headers=H)
    call("POST", f"/api/v1/instances/{sim['id']}/power?action=explode", expect=(422,), headers=H)
if loc:
    call("POST", f"/api/v1/instances/{loc['id']}/power?action=stop", expect=(403,), headers=H)
call("GET", "/api/v1/instances/999999", expect=(404,), headers=H)
call("POST", "/api/v1/instances", headers=H, json={"name": "sweep-node", "instance_type": "t3.small"}, expect=(201,))
call("POST", "/api/v1/instances", headers=H, json={"name": ""}, expect=(422,))

# ---- monitoring
call("GET", "/api/v1/monitoring/summary", headers=H)
call("GET", "/api/v1/monitoring/alerts?limit=10", headers=H)
call("GET", "/api/v1/monitoring/fleet", headers=H)
ths = call("GET", "/api/v1/monitoring/thresholds", headers=H) or []
call("PATCH", "/api/v1/monitoring/thresholds/cpu_percent", headers=H, json={"warning": 70})
call("PATCH", "/api/v1/monitoring/thresholds/cpu_percent", headers=H, json={"warning": 95, "critical": 80}, expect=(422,))
call("PATCH", "/api/v1/monitoring/thresholds/cpu_percent", headers=H, json={"warning_percent": 60}, expect=(422,))
call("POST", "/api/v1/monitoring/collect", headers=H)
if sim:
    call("POST", "/api/v1/monitoring/spike", headers=H, json={"instance_id": sim["id"], "metric": "cpu_percent", "value": 96, "minutes": 2})
    call("POST", "/api/v1/monitoring/spike", headers=H, json={"instance_id": loc["id"], "metric": "cpu_percent", "value": 96, "minutes": 2}, expect=(400, 403, 422))

# ---- security
call("GET", "/api/v1/security/summary", headers=H)
f = call("GET", "/api/v1/security/findings?status=all&page_size=5", headers=H) or {}
items = f.get("items", [])
call("GET", "/api/v1/security/tools", headers=H)
call("GET", "/api/v1/security/report?format=json", headers=H)
call("GET", "/api/v1/security/report?format=csv", headers=H)
call("GET", "/api/v1/security/report?format=xml", expect=(422,), headers=H)
if items:
    fid = items[0]["id"]
    call("PATCH", f"/api/v1/security/findings/{fid}", headers=H, json={"status": "acknowledged"})
    call("PATCH", f"/api/v1/security/findings/{fid}", headers=H, json={"status": "nonsense"}, expect=(422,))
call("POST", "/api/v1/security/scan", headers=H, json={"tools": ["rules"], "include_cloud": True})
call("POST", "/api/v1/security/scan", headers=H, json={"tools": ["nmap"], "include_cloud": True}, expect=(422,))

# ---- costs
call("GET", "/api/v1/costs/summary", headers=H)
call("GET", "/api/v1/costs/trend?months=6", headers=H)
call("GET", "/api/v1/costs/recommendations", headers=H)
call("GET", "/api/v1/costs/pricing", headers=H)
call("PUT", "/api/v1/costs/budget", headers=H, json={"budget_usd": 4200})
call("PUT", "/api/v1/costs/budget", headers=H, json={"budget_usd": -5}, expect=(422,))
call("PATCH", "/api/v1/costs/pricing/t3.small", headers=H, json={"hourly_usd": 0.0208})
call("PATCH", "/api/v1/costs/pricing/t3.small", headers=H, json={"hourly_usd": -1}, expect=(422,))
call("POST", "/api/v1/costs/snapshot", headers=H)

# ---- logs
call("GET", "/api/v1/logs?page_size=5", headers=H)
call("GET", "/api/v1/logs/groups?hours=720", headers=H)
call("GET", "/api/v1/logs/stats?hours=24", headers=H)
call("GET", "/api/v1/logs/services", headers=H)
call("POST", "/api/v1/logs", headers=H, json={"logs": []}, expect=(422,))
call("POST", "/api/v1/logs", headers=H, json={"logs": [{"service": "sweep-svc", "level": "ERROR", "message": "synthetic sweep failure 500"}]})
call("POST", "/api/v1/logs/analyze", headers=H, json={"service": "sweep-svc", "hours": 24})
call("POST", "/api/v1/logs/analyze", headers=H, json={"hours": 24})
call("POST", "/api/v1/logs/analyze", headers=H, json={"hours": 0}, expect=(422,))

# ---- incidents
call("GET", "/api/v1/incidents/stats", headers=H)
inc = call("POST", "/api/v1/incidents", headers=H, json={"title": "Sweep incident", "severity": "medium", "service": "sweep-svc"}, expect=(201,)) or {}
if inc.get("id"):
    iid = inc["id"]
    call("GET", f"/api/v1/incidents/{iid}", headers=H)
    call("POST", f"/api/v1/incidents/{iid}/notes", headers=H, json={"note": "sweep note"})
    call("GET", f"/api/v1/incidents/{iid}/timeline", headers=H)
    call("PATCH", f"/api/v1/incidents/{iid}", headers=H, json={"severity": "high"})
    call("POST", f"/api/v1/incidents/{iid}/status", headers=H, json={"status": "acknowledged"})
    call("POST", f"/api/v1/incidents/{iid}/status", headers=H, json={"status": "closed"}, expect=(409,))
call("GET", "/api/v1/incidents?status=all&page=1&page_size=5", headers=H)

# ---- remediation
call("GET", "/api/v1/remediation/catalog", headers=H)
rules = call("GET", "/api/v1/remediation/rules", headers=H) or []
call("POST", "/api/v1/remediation/rules", headers=H, json={"name": "sweep rule", "metric": "cpu_percent", "operator": ">", "threshold": 95, "action_name": "restart_service"}, expect=(201,))
call("POST", "/api/v1/remediation/rules", headers=H, json={"name": "bad", "metric": "cpu_percent", "operator": ">", "threshold": 95, "action_name": "rm_rf"}, expect=(422,))
call("GET", "/api/v1/remediation/actions", headers=H)
call("POST", "/api/v1/remediation/evaluate", headers=H)
if sim:
    call("POST", "/api/v1/remediation/actions", headers=H, json={"action_name": "restart_service", "instance_id": sim["id"], "dry_run": True}, expect=(201,))

# ---- deployments / pipelines
call("GET", "/api/v1/deployments?page_size=5", headers=H)
call("GET", "/api/v1/deployments/summary", headers=H)
call("GET", "/api/v1/pipelines", headers=H)
call("POST", "/api/v1/deployments", headers=H, json={"service": "sweep-svc", "environment": "staging", "version": "v0.0.1", "status": "success"}, expect=(201,))
call("POST", "/api/v1/deployments", headers=H, json={"service": "", "environment": "staging", "version": "v0", "status": "success"}, expect=(422,))

# ---- aws
call("GET", "/api/v1/aws/status", headers=H)
call("GET", "/api/v1/aws/guide", headers=H)
call("GET", "/api/v1/aws/ec2", headers=H)
call("GET", "/api/v1/aws/s3", headers=H)
call("GET", "/api/v1/aws/iam", headers=H)
call("GET", "/api/v1/aws/security-groups", headers=H)
if sim:
    call("GET", f"/api/v1/aws/cloudwatch?instance_id={sim['id']}&hours=6", headers=H)
call("POST", "/api/v1/aws/refresh", headers=H)

# ---- platform
call("GET", "/api/v1/audit?page_size=5", headers=H)
call("GET", "/api/v1/audit/facets", headers=H)
notes = call("GET", "/api/v1/notifications?limit=5", headers=H) or []
if notes:
    call("POST", f"/api/v1/notifications/{notes[0]['id']}/read", headers=H)
call("POST", "/api/v1/notifications/read-all", headers=H)
call("GET", "/api/v1/settings/runtime", headers=H)
call("GET", "/api/v1/settings", headers=H)
call("PATCH", "/api/v1/settings/log-retention?days=21", headers=H)
call("POST", "/api/v1/settings/cleanup", headers=H)

print("\n" + "=" * 70)
print(f"checked {checked} requests, {len(issues)} issues")
for issue in issues:
    print(" -", issue)
sys.exit(1 if issues else 0)
