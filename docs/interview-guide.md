# Technical interview guide

How to explain CloudOps Sentinel in 2 minutes, then survive the follow-ups.

## 1. The 90-second pitch

> CloudOps Sentinel is a cloud operations platform for AWS teams. It monitors infrastructure, scans for security
> misconfigurations, finds wasted cloud spend, groups and explains application logs, runs an incident workflow,
> and can propose remediation — but every real action is dry-run by default and needs a second human to approve.
>
> The backend is FastAPI with a clean service layer over SQLAlchemy, and the frontend is React + TypeScript with
> a typed API client. It runs entirely locally with SQLite and psutil for real host metrics, plus a clearly
> labelled simulated fleet, so it can be demonstrated without an AWS account or any paid service.
>
> The engineering theme is honesty about data provenance: every row records whether it came from a local host, a
> simulator, a real AWS call, a scanner, or the built-in rule engine — and the API and UI surface that
> distinction everywhere.

## 2. Architecture decision record (verbal)

| Decision | Why | Trade-off |
| --- | --- | --- |
| Service layer separate from routes | Logic testable without HTTP; scheduler reuses the same code | Slightly more files |
| SQLite default, PostgreSQL supported | Zero-install evaluation; production path stays real | A few dialect differences (I branch on `is_sqlite` for hourly bucketing) |
| Simulated fleet instead of mocks | The UI is demonstrable end-to-end without credentials | Must be labelled rigorously — hence the provenance fields |
| Read-only AWS integration | A monitoring tool should not mutate the account it observes | Users must act in the console |
| Allowlist, not blocklist, for remediation | Impossible to invoke an action that was never coded | Less flexible than a script runner |
| JWT + RBAC in dependencies | Centralised, declarative authorisation | No per-resource ACLs yet |

## 3. Likely questions and strong answers

**"How does the monitoring engine work?"**
A lifespan scheduler wakes every N seconds, samples the host with psutil (network throughput is derived from
byte-counter deltas between samples), generates synthetic samples for simulated instances, persists all of them
with a `source` column, classifies health against configurable thresholds, then raises rate-limited
notifications and deduplicated incidents for critical breaches. Rule evaluation runs in the same cycle.

**"How do you avoid fake data?"**
Three mechanisms: a schema-level `source` field on instances, metrics, findings, cost records and deployments; a
scanner contract where a missing tool returns `skipped` with zero findings; and an analysis contract where the
LLM path is only used if configured, otherwise the response says `source: "rule-based"`. The test suite
specifically asserts simulated findings contain the word "simulated" and that unavailable tools report zero.

**"How is remediation safe?"**
Four layers. (1) The registry is an allowlist of seven reversible actions — terminate/delete/IAM/shell do not
exist in the codebase. (2) Every request defaults to `dry_run=true`, which returns a plan and performs no
change. (3) A real execution must transition `pending_approval → approved`, and the approver cannot be the
requester (four-eyes). (4) Execution is health-checked before and after, and written to the audit log. Handlers
only simulate the operation — no AWS mutating API is implemented anywhere.

**"What happens if AWS is down or unconfigured?"**
`connection_status()` returns one of `simulated`, `connected`, `not_configured`, `error`, and every cloud
endpoint degrades to simulated inventory with an explicit message. CloudWatch returns an empty datapoint list
with an explanation rather than inventing numbers. The rest of the platform is unaffected.

**"How do you handle secrets?"**
Nothing is hardcoded; configuration is environment-driven through pydantic-settings. AWS uses boto3's default
chain (instance role preferred). Passwords are PBKDF2-HMAC-SHA256 with 390k iterations and a per-user salt.
`/settings/runtime` masks the DSN and never returns the secret key or AI key. `.env`, Terraform state and
virtualenvs are git-ignored, and compose refuses to start without explicit secrets.

**"Why PBKDF2 instead of bcrypt/argon2?"**
It is in the standard library, so the service has no native build dependency and cannot silently fall back to a
weaker scheme. For a high-security deployment I would move to Argon2id via `argon2-cffi`; the hash format is
versioned (`pbkdf2_sha256$iterations$salt$digest`), so migrating is straightforward.

**"How would you scale this?"**
Move collection out of the API process into a worker (Celery/RQ on the optional Redis) so API latency is
independent of fleet size. Partition `metrics` by time (or move to TimescaleDB), add retention jobs, cache
dashboard aggregates, and replace the in-process rate limiter with Redis. The service layer already has no
FastAPI imports, so lifting it into a worker is a deployment change, not a rewrite.

**"What would you do differently with more time?"**
Real CloudWatch metric ingestion per instance instead of local simulation; a proper job queue for scans;
per-resource ACLs instead of role-only RBAC; and an executor interface so remediation could be wired to SSM
Automation behind the approval gate that already exists.

**"How do you test a system like this?"**
45 pytest tests against a temp SQLite database with the scheduler off. They cover auth and role enforcement,
provenance labelling, metric ordering, alert generation from an injected spike, threshold validation, scanner
outcomes including the skipped path, report downloads, log classification and grouping, analysis fallback, cost
maths, the incident state machine including illegal transitions, and the remediation safety model (allowlist,
dry-run, self-approval refusal, execute-before-approval refusal). CI adds ruff, pip-audit, Bandit, Docker
builds, Trivy and Terraform validation.

## 4. Demo flow for interviews (5 minutes)

1. Sign in, land on Overview — point at the provenance note under the header.
2. Infrastructure — point out `local` (real psutil) versus `simulated` badges, open an instance, show the chart.
3. Monitoring — inject a CPU spike, collect, show the alert appearing and the incident being auto-opened.
4. Security — run a scan, show per-tool outcomes including `skipped`, open a finding's evidence and remediation,
   download the CSV.
5. Cost — show estimates, the budget bar and an idle-resource recommendation with its evidence.
6. Logs — analyse the OOM group, show hypotheses and the "not a confirmed root cause" disclaimer.
7. Remediation — request a dry-run (no change), then a real action; point at `pending_approval`; show that the
   requester cannot approve it; approve as admin, execute, show `[SIMULATED]` and the audit entry.
8. Audit — filter to `remediation.approved` to close the loop.

## 5. Numbers to have ready

* 17 tables, 45 backend tests, 14 pages, ~80 API routes.
* Default collection interval 15s, 72h metric retention, 10-minute alert dedupe window.
* Remediation: 7 allowlisted actions, 0 destructive ones, approval mandatory for non-dry-run.
* Scan tools: 2 built-in + 4 external (Bandit, pip-audit, Checkov, Trivy).
