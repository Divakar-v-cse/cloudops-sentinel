# API reference

Base URL: `http://127.0.0.1:8000/api/v1` · interactive docs at `/docs` (Swagger) and `/redoc`.

## Authentication

All endpoints except `/health`, `/metrics`, `/` and `POST /auth/login` require a bearer token.

```bash
curl -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@cloudops.local","password":"Admin@12345"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {"id": 1, "email": "admin@cloudops.local", "full_name": "Platform Administrator",
           "role": "admin", "is_active": true, "must_change_password": true}
}
```

Send it as `Authorization: Bearer <token>`. Tokens are HS256, expire after
`ACCESS_TOKEN_EXPIRE_MINUTES` (480 by default), and carry the role claim.

### Roles

| Role | Read | Operate (scan/collect/incidents/remediation) | Admin (thresholds, budget, users, settings) |
| --- | --- | --- | --- |
| `viewer` | ✅ | — | — |
| `analyst` | ✅ | ✅ incidents, logs, analysis | — |
| `engineer` | ✅ | ✅ | — |
| `admin` | ✅ | ✅ | ✅ |

## Errors

| Status | Meaning |
| --- | --- |
| 400 | Business-rule violation (e.g. resolving without a summary) |
| 401 | Missing/invalid/expired token, or bad credentials |
| 403 | Authenticated but the role is insufficient, or self-approval attempted |
| 404 | Entity not found |
| 409 | Illegal state transition (e.g. `detected → closed`, execute before approval) |
| 422 | Validation error (Pydantic detail array) |
| 500 | Unhandled server error (generic message; details stay in logs) |

---

## Auth

| Method | Path | Role | Description |
| --- | --- | --- | --- |
| POST | `/auth/login` | public | Email + password → JWT |
| POST | `/auth/token` | public | OAuth2 password form (for Swagger "Authorize") |
| GET | `/auth/me` | any | Current user |
| POST | `/auth/change-password` | any | Rotate own password |
| GET | `/auth/users` | admin, engineer | List users |
| POST | `/auth/users` | admin | Create user |
| PATCH | `/auth/users/{id}/status?active=` | admin | Enable/disable |

## Dashboard

| Method | Path | Description |
| --- | --- | --- |
| GET | `/dashboard/overview` | Instances, utilisation, incidents, security, cost, deployments, alerts, 12h trend, recent items |
| GET | `/dashboard/trend?hours=12` | Fleet CPU/memory/disk hourly averages |

## Instances

| Method | Path | Description |
| --- | --- | --- |
| GET | `/instances?source=&environment=&health=&search=` | Inventory |
| GET | `/instances/{id}` | Metadata + latest metric + per-instance alerts + statistics + provenance note |
| GET | `/instances/{id}/metrics?hours=6` | Time-ordered samples |
| POST | `/instances` | Add **simulated** instance (real ones are discovered via AWS) |
| PATCH | `/instances/{id}` | Rename / environment / tags |
| POST | `/instances/{id}/power?action=start\|stop\|reboot` | Simulated only (403 for local/aws) |
| DELETE | `/instances/{id}` | Simulated only |

## Monitoring

| Method | Path | Description |
| --- | --- | --- |
| GET | `/monitoring/summary` | Fleet health, thresholds, intervals, sample count |
| GET | `/monitoring/alerts?limit=20` | Live threshold breaches derived from latest samples |
| GET | `/monitoring/metrics?instance_id=&hours=&limit=` | Raw samples |
| GET | `/monitoring/fleet` | Latest sample per instance |
| GET | `/monitoring/thresholds` | Configured thresholds |
| PATCH | `/monitoring/thresholds/{metric}` | Admin: warning/critical/enabled |
| POST | `/monitoring/collect` | Run a collection cycle now |
| POST | `/monitoring/spike` | Inject a synthetic breach (simulated instances only) |

## Security

| Method | Path | Description |
| --- | --- | --- |
| GET | `/security/findings?severity=&status=&category=&source_kind=&search=&page=` | Paginated findings |
| GET | `/security/summary` | Risk score, counts, categories, last scan |
| GET | `/security/findings/{id}` | Single finding |
| PATCH | `/security/findings/{id}` | `open`, `acknowledged`, `resolved`, `false_positive` |
| POST | `/security/scan` | Run selected scanners |
| GET | `/security/tools` | Availability probe |
| GET | `/security/report?format=json\|csv` | Download report |

Scan request/response:

```bash
curl -X POST localhost:8000/api/v1/security/scan -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tools":["rules","aws","bandit","pip-audit","checkov","trivy"],"include_cloud":true}'
```

```json
{
  "scan_id": "436351c196584877",
  "findings_created": 0,
  "findings_updated": 10,
  "findings_resolved": 0,
  "tools": [
    {"tool": "sentinel-iac-rules", "status": "executed", "reason": null, "findings": 0, "duration_ms": 0},
    {"tool": "aws-config-audit", "status": "executed", "reason": "simulated inventory used", "findings": 9, "duration_ms": 0},
    {"tool": "bandit", "status": "executed", "reason": null, "findings": 1, "duration_ms": 3843},
    {"tool": "trivy", "status": "skipped", "reason": "trivy binary is not installed in this environment", "findings": 0, "duration_ms": 0}
  ],
  "simulated_resources": true,
  "aws_connected": false
}
```

`status` is `executed`, `skipped` or `failed`. A non-executed tool always reports `findings: 0`.

## Costs

| Method | Path | Description |
| --- | --- | --- |
| GET | `/costs/summary` | Estimate, MTD, forecast, budget, savings, breakdown |
| GET | `/costs/trend?months=6` | Monthly series |
| GET | `/costs/recommendations` | Idle / oversized / scheduling / commitment |
| GET | `/costs/pricing` | Pricing assumptions |
| PATCH | `/costs/pricing/{instance_type}` | Admin |
| PUT | `/costs/budget` | Admin |
| POST | `/costs/snapshot` | Persist current estimate into history |

## Logs

| Method | Path | Description |
| --- | --- | --- |
| POST | `/logs` | Ingest up to 500 records |
| GET | `/logs?query=&service=&severity=&level=&hours=&page=` | Search |
| GET | `/logs/groups?hours=24&service=` | Fingerprint groups |
| GET | `/logs/stats?hours=24` | Totals, per-severity, top services, hourly timeline |
| GET | `/logs/services` | Distinct services |
| POST | `/logs/analyze` | AI or rule-based analysis |
| POST | `/logs/retention/cleanup?days=` | Admin |

Ingest payload:

```json
{
  "logs": [
    {"service": "checkout-api", "level": "ERROR", "message": "Payment provider timeout after 3000ms",
     "trace_id": "trc-1", "timestamp": "2026-11-18T10:00:00Z", "metadata": {"region": "eu-west-1"}}
  ]
}
```

Analysis payload (any one selector):

```json
{"fingerprint": "9f2c...", "hours": 24}
{"service": "order-worker", "hours": 24}
{"log_ids": [12, 13, 14]}
```

Response includes `source` (`ai` / `rule-based`), `summary`, `likely_causes`, `hypotheses[]`,
`debug_commands[]`, `next_steps[]`, `confidence`, a mandatory `disclaimer`, and `related_incidents[]`.

## Incidents

| Method | Path | Description |
| --- | --- | --- |
| GET | `/incidents?status=&severity=&service=&search=&page=` | List |
| GET | `/incidents/stats` | Open counts, MTTA, MTTR, 7-day volume, risk score |
| POST | `/incidents` | Create (analyst+) |
| GET | `/incidents/{id}` | Detail with notes and duration |
| PATCH | `/incidents/{id}` | Severity / assignee / service / title |
| POST | `/incidents/{id}/status` | Validated transition |
| POST | `/incidents/{id}/notes` | Investigation note |
| GET | `/incidents/{id}/timeline` | Notes only |

Allowed transitions: `detected → acknowledged|investigating|resolved`, `acknowledged → investigating|resolved`,
`investigating → resolved`, `resolved → closed|investigating`, `closed → detected`. Resolving requires a
summary. Everything else returns 409.

## Remediation

| Method | Path | Description |
| --- | --- | --- |
| GET | `/remediation/catalog` | Allowlisted actions with risk metadata |
| GET | `/remediation/rules` | Rules |
| POST | `/remediation/rules` | Create (action validated against the registry) |
| PATCH | `/remediation/rules/{id}` | Enable/threshold/dry-run |
| DELETE | `/remediation/rules/{id}` | Delete |
| GET | `/remediation/actions?status=&page=` | History |
| POST | `/remediation/actions` | Dry-run or approval request |
| POST | `/remediation/actions/{id}/approve` | Approver ≠ requester |
| POST | `/remediation/actions/{id}/reject` | |
| POST | `/remediation/actions/{id}/execute` | Approved or dry-run only |
| POST | `/remediation/evaluate` | Evaluate rules now |

Request:

```json
{"action_name": "restart_service", "instance_id": 2, "dry_run": true, "reason": "CPU saturated"}
```

`dry_run=true` executes immediately in plan mode returning `status: "dry_run"` and an output ending
`No change was made`. `dry_run=false` returns `status: "pending_approval"`.

## Deployments and pipelines

| Method | Path | Description |
| --- | --- | --- |
| GET | `/deployments?service=&environment=&status=&page=` | History |
| GET | `/deployments/summary` | Totals, success rate, last deployment |
| POST | `/deployments` | Ingest a CI run (`source=pipeline`) |
| GET | `/pipelines` | Definitions detected from the repository + run stats |

## AWS

| Method | Path | Description |
| --- | --- | --- |
| GET | `/aws/status` | `simulated` / `connected` / `not_configured` / `error` |
| GET | `/aws/ec2` | Inventory (read-only) |
| GET | `/aws/s3` | Buckets with public-access and encryption flags |
| GET | `/aws/iam` | Customer-managed policies with risky statements |
| GET | `/aws/security-groups` | Ingress rules |
| GET | `/aws/cloudwatch?instance_id=&hours=&metric=` | Datapoints, or an explicit "connected mode only" message |
| POST | `/aws/refresh` | Admin: re-check credentials |
| GET | `/aws/guide` | Setup steps and required permissions |

## Platform

| Method | Path | Description |
| --- | --- | --- |
| GET | `/audit?action=&entity_type=&actor=&search=&page=` | Audit trail |
| GET | `/audit/facets` | Action/entity counts |
| GET | `/notifications?unread_only=&limit=` | In-app notifications |
| POST | `/notifications/{id}/read` · `/notifications/read-all` | Mark read |
| GET | `/settings` (admin) · `/settings/runtime` (any) | Runtime config, masked DSN, tool availability |
| PATCH | `/settings/log-retention?days=` | Admin |
| POST | `/settings/cleanup` | Admin |

## Non-versioned endpoints

| Path | Purpose |
| --- | --- |
| `/` | Product metadata and current AWS mode |
| `/health` | Liveness with database probe |
| `/metrics` | Prometheus exposition (instance counts, open incidents, findings, sample count) |
