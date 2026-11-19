# Installation and configuration guide

## 1. Prerequisites

| Tool | Version | Required? |
| --- | --- | --- |
| Python | 3.12 | Yes |
| Node.js | 20 or 22 | Yes (frontend) |
| Docker Desktop / Engine | 24+ | Only for container path |
| Terraform | 1.6+ | Only to plan infrastructure |
| kubectl | 1.28+ | Only for Kubernetes |
| Trivy | 0.50+ | Optional scanner |

Nothing else is required. No paid service, no AWS account, no LLM key.

## 2. Local setup (recommended when evaluating)

```bash
# 1. clone
git clone https://github.com/Divakar-v-cse/cloudops-sentinel.git
cd cloudops-sentinel

# 2. python environment
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# 3. configuration
cp .env.example backend/.env       # Windows: copy .env.example backend\.env
# edit backend/.env: SECRET_KEY, DEFAULT_ADMIN_PASSWORD at minimum

# 4. run the API (terminal 1)
cd backend
PYTHONPATH=. uvicorn app.main:app --port 8000 --reload

# 5. run the UI (terminal 2)
cd frontend
npm install
npm run dev
```

URLs:

| Service | URL |
| --- | --- |
| UI | http://localhost:5173 |
| API | http://127.0.0.1:8000 |
| Swagger | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| Health | http://127.0.0.1:8000/health |
| Prometheus text | http://127.0.0.1:8000/metrics |

First startup creates the schema and seeds: 4 roles, 3 users, 8 simulated instances, the local host, ~500
telemetry samples, 17 log templates across 7 services, 4 incidents, 9 security findings, 3 remediation rules,
9 deployments and 3 pricing/history months. Re-running is idempotent — seeds are skipped when data exists.

### Default accounts

Passwords come from `.env`; the development fallbacks are shown here for first login.

| Email | Role | Password source |
| --- | --- | --- |
| `admin@cloudops.local` | admin | `DEFAULT_ADMIN_PASSWORD` (fallback `Admin@12345`) |
| `engineer@cloudops.local` | engineer | `DEFAULT_ADMIN_PASSWORD` (fallback `Admin@12345`) |
| `analyst@cloudops.local` | analyst | `DEFAULT_ANALYST_PASSWORD` (fallback `Analyst@12345`) |

All seeded users have `must_change_password=true`. Change them before any shared deployment.

### If port 8000 is busy

```powershell
# Windows
$env:VITE_PROXY_TARGET="http://127.0.0.1:8010"; npm run dev
```
```bash
# POSIX
VITE_PROXY_TARGET=http://127.0.0.1:8010 npm run dev
```

## 3. PostgreSQL instead of SQLite

```bash
createdb cloudops
export DATABASE_URL="postgresql+psycopg://sentinel:password@localhost:5432/cloudops"
cd backend && alembic upgrade head && PYTHONPATH=. uvicorn app.main:app --port 8000
```

`psycopg` (v3) is already in `requirements.txt`. The app also creates missing tables at startup, so Alembic is
recommended for controlled environments rather than strictly required for a first run.

## 4. Docker Compose

```bash
cp .env.example .env
# set SECRET_KEY, POSTGRES_PASSWORD, DEFAULT_ADMIN_PASSWORD — compose refuses to start without them
docker compose up -d --build
docker compose --profile cache up -d redis   # optional
```

| Service | Port | Notes |
| --- | --- | --- |
| frontend | 8080 | nginx, proxies `/api/` to backend, security headers |
| backend | 8000 | non-root user, healthcheck on `/health` |
| postgres | internal | named volume `postgres_data`, `pg_isready` healthcheck |
| redis | internal | optional profile `cache` |

Logs: `docker compose logs -f backend`. Reset data: `docker compose down -v` (**deletes the database volume**).

## 5. Kubernetes (optional; no paid cluster needed)

```bash
kind create cluster --name sentinel
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl -n cloudops-sentinel create secret generic sentinel-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24)" \
  --from-literal=DATABASE_URL="postgresql+psycopg://sentinel:<password>@postgres:5432/cloudops" \
  --from-literal=DEFAULT_ADMIN_PASSWORD="<strong-password>"
kubectl apply -k infrastructure/kubernetes
kubectl -n cloudops-sentinel port-forward svc/frontend 8080:80
```

Images referenced by the manifests are placeholders (`ghcr.io/example/...`); build and retag them locally or
set your own registry before applying. HPAs require the metrics-server add-on.

## 6. AWS configuration (optional, read-only)

1. Create a role with `SecurityAudit` + `ReadOnlyAccess` (or the narrower policy in
   `infrastructure/terraform/iam.tf`).
2. Attach it to the host running Sentinel, or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the shell
   (never in a file that is committed).
3. Set `AWS_REGION` and `AWS_SIMULATION_MODE=false`, restart the backend.
4. `GET /api/v1/aws/status` must report `"mode": "connected"` before trusting any cloud panel.

**AWS services that can incur charges if you apply the Terraform:** VPC (free), subnets/IGW (free), security
groups (free), S3 storage and requests (pennies at demo scale), EC2 instances (`instance_count` defaults to
**0** — only charged if you raise it), CloudWatch alarms (first 10 free, then ~$0.10/alarm/month), SNS email
(first 1,000 notifications free). CloudWatch `GetMetricStatistics` calls are charged per API request at scale.
Nothing is applied automatically; `terraform apply` is your decision.

## 7. Optional AI log analysis

```env
AI_PROVIDER=openai-compatible
AI_API_KEY=sk-...
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
```

Without these, `/api/v1/logs/analyze` returns `source: "rule-based"` with deterministic hypotheses. The UI shows
which path produced the answer.

## 8. Verification after install

```bash
curl -s localhost:8000/health | jq
# {"status":"ok", ..., "database":"ok", ...}

TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@cloudops.local","password":"Admin@12345"}' | jq -r .access_token)
curl -s localhost:8000/api/v1/dashboard/overview -H "Authorization: Bearer $TOKEN" | jq '.instances'
```

Expected: `{"total": 9, "by_source": {"local": 1, "simulated": 8, ...}}`.

## 9. Test and build commands

```bash
cd backend
PYTHONPATH=. ../.venv/Scripts/python.exe -m pytest      # 59 tests
ruff check app tests

cd ../frontend
npm run build

# optional
python tests/integration/live_api_check.py --base-url http://127.0.0.1:8000
```
