# CloudOps Sentinel

**AI-assisted AWS cloud infrastructure monitoring, security, cost optimisation, incident management and
approval-gated auto-remediation platform.**

CloudOps Sentinel is a working full-stack platform, not a mockup: a FastAPI backend with real monitoring,
scanning and analysis engines, a PostgreSQL/SQLite schema, and a React + TypeScript operations console with
14 connected pages. It runs entirely in **local mode** with no paid services, and every piece of simulated data
is labelled wherever it appears.

---

## 1. What it actually does

| Module | Implementation | Data honesty |
| --- | --- | --- |
| **Monitoring** | Real CPU/memory/disk/network/uptime sampling of this host through `psutil`, plus a deterministic simulator for a demo fleet. Threshold evaluation creates notifications and deduplicated incidents. | `source=local` vs `source=simulated` on every metric row |
| **AWS integration** | `boto3` EC2/S3/IAM/security-group/CloudWatch inventory with least-privilege read-only calls, connection diagnostics and graceful degradation. | `source=aws` only when a real account answered; otherwise `simulated` |
| **Security scanning** | Executes Bandit, pip-audit, Checkov and Trivy as subprocesses and parses their JSON. Built-in policy engine audits Terraform/Dockerfiles and AWS config (public S3, open SSH/RDP, wildcard IAM, encryption). JSON/CSV exports. | Tool name + `source_kind` = `tool` / `aws` / `rule-engine` / `simulated`; missing tools report `skipped` |
| **Cost intelligence** | Editable pricing model, monthly estimates, 4-month history, budget tracking, idle/oversized/off-hours/commitment recommendations from real utilisation samples. | Always marked **estimated**; no billing figure is invented |
| **Log intelligence** | Batched ingestion, fingerprint grouping, severity classification, filtering, optional OpenAI-compatible analysis with a deterministic rule-based fallback (9 known failure signatures). | `source=ai` only when a provider answered, otherwise `rule-based` |
| **Incidents** | Enforced lifecycle `DETECTED → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED`, timeline notes, MTTA/MTTR, auto-opening from monitoring. | Every transition validated and audited |
| **Remediation** | Allowlisted action registry, dry-run by default, health check before/after, four-eyes approval, full audit trail. Destructive cloud operations are not implemented at all. | `[SIMULATED]` prefix on every execution output |
| **Deployments / CI-CD** | Pipeline definitions detected from the repository, deployment ingestion endpoint, success rate and history. | `source=pipeline` for real ingests, `simulated` for seeded rows |

### Architecture

```
React 18 + TypeScript + Vite + Tailwind + Recharts + React Router
        │  Axios (JWT bearer)
        ▼
FastAPI  ── /api/v1 ──►  Auth · Instances · Monitoring · Security · Costs · Logs
        │                Incidents · Remediation · Deployments · AWS · Audit · Settings
        │
        ├── Services (business logic, no HTTP concerns)
        │     monitoring · aws · security_scan · cost · logs · incidents · remediation
        │     deployments · bootstrap
        │
        ├── SQLAlchemy 2.0 models + Alembic migration
        │     SQLite (default, zero-install) or PostgreSQL 16
        │
        └── psutil (real host) · boto3 (optional AWS) · Bandit/pip-audit/Checkov/Trivy
```

Clean separation: routes only validate/authorise and delegate; all logic lives in `app/services`.

---

## 2. Quick start (local mode, no Docker required)

Requirements: Python 3.12, Node 20+ (Node 22 tested).

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt

copy .env.example backend\.env          # then edit secrets
cd backend
$env:PYTHONPATH="."
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```

```powershell
# second terminal
cd frontend
npm install
npm run dev            # http://localhost:5173  (proxies /api -> 127.0.0.1:8000)
```

### Linux / macOS

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp .env.example backend/.env        # edit secrets
cd backend && PYTHONPATH=. uvicorn app.main:app --port 8000 --reload
# second terminal: cd frontend && npm install && npm run dev
```

First start creates the schema, seeds roles/users, 8 simulated instances, ~500 telemetry samples, log history,
incidents, findings, rules and deployments. It is idempotent.

**Seeded accounts** (passwords come from `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_ANALYST_PASSWORD` in `.env`;
the built-in development fallback is `Admin@12345` / `Analyst@12345`):

| Email | Role | Capabilities |
| --- | --- | --- |
| `admin@cloudops.local` | admin | everything, including thresholds, budget, users |
| `engineer@cloudops.local` | engineer | operate, request/approve remediation |
| `analyst@cloudops.local` | analyst | investigate incidents and logs |

Change these before exposing the service. `GET /api/v1/settings/runtime` surfaces a warning while the
development `SECRET_KEY` or default admin password is still in use.

If port 8000 is already taken, use another port and point the frontend at it:

```powershell
$env:VITE_PROXY_TARGET="http://127.0.0.1:8010"; npm run dev
```

---

## 3. Configuration

Everything is environment driven (`backend/.env` for the API process, root `.env` for Docker Compose).
See [.env.example](.env.example). Nothing is hardcoded; the only defaults are non-sensitive development
placeholders which the runtime warns about.

Key settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | development placeholder | JWT signing — **replace in any shared environment** |
| `DATABASE_URL` | `sqlite:///…/cloudops.db` | Use `postgresql+psycopg://…` for Postgres |
| `ENABLE_SCHEDULER` | `true` | Background collection + rule evaluation |
| `MONITORING_INTERVAL_SECONDS` | `15` | Collection cadence |
| `AWS_SIMULATION_MODE` | `true` | Must be explicitly disabled to touch a real account |
| `AWS_REGION` | `us-east-1` | Region for boto3 clients |
| `AI_PROVIDER` / `AI_API_KEY` | `none` / empty | Optional LLM log explanation |
| `COST_BUDGET_USD` | `3000` | Budget threshold used by the cost page |
| `LOG_RETENTION_DAYS` | `14` | Default retention window |

---

## 4. API

Interactive docs: **http://127.0.0.1:8000/docs** · health: `/health` · Prometheus text: `/metrics`.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@cloudops.local","password":"Admin@12345"}' | jq -r .access_token)

curl -s localhost:8000/api/v1/dashboard/overview -H "Authorization: Bearer $TOKEN" | jq
curl -s -X POST localhost:8000/api/v1/security/scan -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"tools":["rules","aws","bandit"],"include_cloud":true}' | jq
curl -s -X POST localhost:8000/api/v1/logs/analyze -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"service":"order-worker","hours":24}' | jq
```

Selected endpoints (full list in `/docs`):

```
POST /api/v1/auth/login                      JWT issue
GET  /api/v1/dashboard/overview              all module aggregates
GET  /api/v1/instances/{id}                  metadata + latest metric + alerts
GET  /api/v1/monitoring/alerts               live threshold breaches
PATCH/api/v1/monitoring/thresholds/{metric}  admin only
POST /api/v1/security/scan                   run scanners, returns per-tool status
GET  /api/v1/security/report?format=csv      downloadable report
GET  /api/v1/costs/recommendations           savings opportunities
POST /api/v1/logs                            batch ingest (≤500)
POST /api/v1/incidents/{id}/status           validated lifecycle transition
POST /api/v1/remediation/actions             dry-run or approval request
POST /api/v1/remediation/actions/{id}/approve|reject|execute
POST /api/v1/deployments                     ingest a pipeline run
GET  /api/v1/aws/status|ec2|s3|iam|security-groups|cloudwatch
GET  /api/v1/audit                           filterable audit trail
```

---

## 5. Tests, lint and build

```bash
cd backend
PYTHONPATH=. ../.venv/Scripts/python.exe -m pytest      # 45 tests
../.venv/Scripts/python.exe -m ruff check app tests
cd ../frontend && npm run build                          # tsc + vite production build
```

The suite exercises authentication and role enforcement, inventory provenance, metric ordering, alert
generation from an injected spike, threshold validation, scan tool outcomes, downloadable reports, log
classification and grouping, fallbacks, cost maths, the incident state machine (including illegal
transitions), the remediation safety model (allowlist, dry-run, four-eyes approval), pipelines, audit and
secret masking. It runs against a temporary SQLite database with the scheduler disabled.

Verified locally: **45/45 tests pass, `ruff` clean, frontend production build succeeds**, and a browser
walk-through of all 12 authenticated routes produced **zero console errors**.

---

## 6. Containers and orchestration

```bash
cp .env.example .env        # set SECRET_KEY, POSTGRES_PASSWORD, DEFAULT_ADMIN_PASSWORD
docker compose up -d --build
# UI http://localhost:8080 · API http://localhost:8000/docs
docker compose --profile cache up -d redis   # optional Redis
```

* PostgreSQL 16 with a named volume and `pg_isready` health check.
* Backend and frontend images run as non-root users with health checks and `unless-stopped` restart policies.
* The frontend nginx image serves the SPA, proxies `/api/`, and sends security headers.
* Compose refuses to start without `POSTGRES_PASSWORD`, `SECRET_KEY` and `DEFAULT_ADMIN_PASSWORD`.

Kubernetes (optional, no paid cluster required — works with kind/minikube):

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl -n cloudops-sentinel create secret generic sentinel-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24)" \
  --from-literal=DATABASE_URL="postgresql+psycopg://sentinel:<password>@postgres:5432/cloudops" \
  --from-literal=DEFAULT_ADMIN_PASSWORD="<strong-password>"
kubectl apply -k infra/k8s
```

Manifests include namespace, ConfigMap, Secret references (example only, never applied), PostgreSQL
StatefulSet, backend/frontend Deployments with requests/limits and readiness/liveness/startup probes, Services,
and HPAs. `secret.example.yaml` is deliberately excluded from `kustomization.yaml` so placeholder values cannot
be applied by accident.

### Terraform

`infra/terraform` provisions (only when you apply it): VPC, public subnets, restricted security group, an
optional encrypted EC2 host (`instance_count` defaults to **0**, so a plan creates no compute cost), an
encrypted private S3 bucket with lifecycle rules, a read-only IAM role, SNS topic and CloudWatch alarms.

```bash
cd infra/terraform
terraform init && terraform fmt -check && terraform validate
terraform plan -out tf.plan
```

Never applied automatically by the platform.

---

## 7. CI/CD

* **GitHub Actions** — `.github/workflows/ci.yml`: backend ruff + pytest, frontend install/build, pip-audit
  and Bandit reports, Docker builds, Trivy image/fs scans, `terraform fmt -check` + `validate`, compose and
  Kubernetes manifest validation.
* **Release** — `.github/workflows/release.yml`: builds and pushes both images to GHCR, deploys staging, then
  requires the `production` environment's manual approval before rolling out and smoke-testing `/health`.
* **Jenkins** — `Jenkinsfile`: checkout, build, lint, test (JUnit), frontend build, Docker image creation,
  Trivy + Bandit + pip-audit, Terraform validation, approval gate for production, deploy, smoke test. All
  credentials are injected with `withCredentials` and never echoed.

---

## 8. Security and safety model

1. **No automatic destructive action.** The remediation registry contains only reversible operations
   (`restart_service`, `recycle_connection_pool`, `clear_cache`, `rotate_logs`, `scale_out_replicas`,
   `rollback_deployment`, `run_health_check`). `terminate_instance`, `delete_bucket`, IAM/security-group
   mutation and arbitrary shell are not implemented and are rejected with HTTP 422.
2. **Dry-run first.** Actions default to `dry_run=true` and return a plan with `No change was made`.
3. **Four-eyes approval.** Any real execution needs `pending_approval → approved`, and the approver cannot be
   the requester. Execution is refused before approval.
4. **No AWS mutation.** The AWS module only calls read APIs (`Describe*`, `List*`, `Get*`, `sts:GetCallerIdentity`);
   SNS publish exists but is only invoked manually and is disabled without `SNS_TOPIC_ARN`.
5. **Audit everything.** Logins, scans, threshold changes, incident transitions, remediation decisions and
   settings changes are written to `audit_logs` with actor, entity and structured detail.
6. **RBAC.** `admin` / `engineer` / `analyst` / `viewer`, enforced by FastAPI dependencies.
7. **Passwords** use PBKDF2-HMAC-SHA256 (390k iterations, per-user salt); JWTs are HS256 with expiry.
8. **Headers** — `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`,
   plus a CSP in the nginx image.
9. **No secrets in the database or logs.** AWS credentials come from boto3's default chain only.

---

## 9. Project layout

```
backend/
  app/
    api/deps.py, router.py, routes/        HTTP layer (auth, instances, monitoring, security,
                                           costs, logs, incidents, remediation, deployments,
                                           aws, platform)
    core/                                  settings, security, utilities
    db/session.py                          engine + session factory
    models/                                identity, infra, operations (17 tables)
    schemas/                               Pydantic request/response contracts
    services/                              monitoring, aws, security_scan, cost, logs,
                                           incidents, remediation, deployments, dashboard,
                                           audit, notifications, bootstrap
    main.py                                app factory, lifespan scheduler, /health, /metrics
  alembic/                                 migration environment + initial revision
  tests/                                   45 pytest tests
frontend/
  src/
    api/client.ts, endpoints.ts            typed API layer
    components/                            Layout, UI kit, charts, icons
    context/                               auth, theme, toasts
    pages/                                 14 pages (login + 13 authenticated)
    lib/format.ts                          UTC-safe formatting
infra/
  terraform/                               VPC, EC2 (opt-in), S3, IAM, CloudWatch, SNS
  k8s/                                     namespace, config, statefulset, deployments, HPA
.github/workflows/                         ci.yml, release.yml
Jenkinsfile · docker-compose.yml · .env.example
```

---

## 10. Limitations (stated, not hidden)

* The seeded fleet is **simulated**. It exists so the product can be evaluated without an AWS account; it is
  never presented as real infrastructure.
* Cost figures are **estimates** from the editable pricing table, not AWS invoices. Cost Explorer integration
  requires `ce:GetCostAndUsage` and is read-only when connected.
* AI log analysis is optional. Without `AI_PROVIDER`/`AI_API_KEY` the deterministic rule engine answers, and the
  UI labels the source.
* Trivy is a standalone binary; when it is absent, scans report it as `skipped` with findings `= 0`.
* Remediation executes simulations only. Wiring a real executor would require adding a reviewed handler, plus
  the approval path that already exists.
* SQLite is the zero-install default. For concurrent production use, set `DATABASE_URL` to PostgreSQL and run
  `alembic upgrade head` (the app also creates missing tables at startup for local mode).

---

## 11. Acceptance criteria status

| Requirement | Status |
| --- | --- |
| Real monitoring engine (psutil + simulator), history, thresholds, alerts | ✅ |
| Optional AWS integration with graceful degradation and provenance | ✅ |
| Security scanner with real tools, built-in rules, JSON/CSV reports | ✅ |
| Cost dashboard with assumptions, idle detection, savings | ✅ |
| Log ingestion, search, grouping, AI + deterministic analysis | ✅ |
| Incident lifecycle with timeline, notes, audit | ✅ |
| Safe remediation with allowlist, dry-run, approval, history | ✅ |
| GitHub Actions + Jenkins pipelines, Trivy, terraform validation | ✅ |
| Docker, Compose, Kubernetes, HPAs, probes | ✅ |
| 14 functional pages, every one backed by APIs | ✅ |
| 17 SQLAlchemy models, Alembic migration, indexes | ✅ |
| JWT auth, RBAC, hashed passwords | ✅ |
| Tests passing, lint clean, production build | ✅ |

---

*CloudOps Sentinel — local-first, honest about its data, safe by default.*
