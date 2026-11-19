# Troubleshooting

## Startup

**`[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)`**
Something else owns port 8000. Use another port and point the UI at it:
```powershell
uvicorn app.main:app --port 8010
$env:VITE_PROXY_TARGET="http://127.0.0.1:8010"; npm run dev
```

**`ModuleNotFoundError: No module named 'app'`**
`PYTHONPATH` is not set to the `backend` directory. Run from `backend/` with `PYTHONPATH=.` (PowerShell:
`$env:PYTHONPATH="."`).

**`ValidationError ... SECRET_KEY` / startup warnings**
These are warnings, not failures. `insecure_defaults` reports that the development `SECRET_KEY` or default
admin password is still in use. Set them in `.env` before any shared deployment.

**Empty UI after login / dashboard shows no instances**
Check `/api/v1/instances` directly with your token. If it returns `[]`, the seed did not run (existing empty
database with a failed bootstrap). Delete the database file and restart:
```powershell
Remove-Item backend\cloudops.db   # local SQLite only — destroys local data
```
Inspect `docker compose logs backend` when running containers.

## Authentication

**401 on every request** — token missing, expired, or signed with a different `SECRET_KEY` (happens after
changing the key). Sign in again.

**403 on threshold save / budget / users** — those endpoints are admin-only. Use `admin@cloudops.local` or a
user with the `admin` role.

**403 "the requester cannot approve their own production action"** — by design (four-eyes). Approve with a
different account.

## Frontend

**Blank page, `Failed to fetch` in console** — the API is not reachable at the proxy target. Confirm
`http://127.0.0.1:8000/health` responds, then restart `npm run dev`.

**CORS error in dev** — you are calling the API cross-origin without the Vite proxy. Either use `/api/v1` with
`VITE_PROXY_TARGET`, or add your origin to `CORS_ORIGINS`.

**`npm run build` fails on a type** — run `npx tsc -b` in `frontend/` to see the exact file and line. The build
is strict TypeScript.

**Everything looks unlabelled** — simulated rows always render a `simulated` badge. If a cloud panel shows no
badge and no data, the AWS call failed; check `/api/v1/aws/status`.

**PATCH returns 200 but nothing changed** — fixed in this build. Request schemas now reject unknown fields
with 422, so a mistyped key (for example `warning_percent` instead of `warning`) fails loudly instead of silently
doing nothing.

**`/aws/cloudwatch?instance_id=7` returns 422** — fixed. The parameter accepts either a Sentinel row id (digits)
or an AWS instance id (`i-...`), and resolves the former to `external_id` when the resource was imported from AWS.

## Monitoring

**No new metrics** — the scheduler is disabled (`ENABLE_SCHEDULER=false`) or the interval is long. Trigger
`POST /api/v1/monitoring/collect` or press "Collect now" in the UI.

**All local metrics are zero on first sample** — `psutil.cpu_percent(interval=None)` needs a previous call to
compute a delta; the first sample after boot reads 0. The next collection is accurate.

**Alerts keep repeating** — notification deduplication is 10 minutes per instance/signal/level. Check
`current_alerts` for the derived live view rather than the notification feed.

## Security scanning

**`trivy` reports `skipped`** — the binary is not installed. Install it (`brew install trivy`,
`winget install AquaSecurity.Trivy`, or the release binary) and rescan. The platform never fabricates its output.

**`pip-audit` fails or times out** — it needs network access to the advisory service. Offline environments
should expect `failed` with a reason, which is accurate rather than a fake pass.

**Bandit reports an issue in `core/config.py`** — expected: the file contains development placeholder defaults
for `SECRET_KEY` and the admin password. They are overridable and flagged at startup; the finding documents a
real (accepted, documented) risk rather than a false negative.

**Checkov skipped** — `checkov` is not installed. `pip install checkov`, then rescan.

## AWS

**`mode: not_configured`** — no credentials in boto3's chain. Export keys or attach an instance role, then set
`AWS_SIMULATION_MODE=false` and restart. `POST /api/v1/aws/refresh` re-checks without a restart.

**`mode: error`** — credentials exist but the API call failed (expired key, wrong region, missing
`sts:GetCallerIdentity`). The message includes the AWS error.

**S3/IAM lists are empty in connected mode** — the role lacks `s3:GetBucketAcl` / `iam:ListPolicies` etc. See
`GET /api/v1/aws/guide` for the exact permission list.

## Remediation

**`422 action 'x' is not in the allowlisted action registry`** — intentional. Destructive operations are not
implemented.

**`409 Action is pending_approval; only approved or dry-run actions can be executed`** — approve it first with a
different user.

**Execution output says `[SIMULATED]`** — correct. This build simulates execution and never calls a cloud API.

## Containers

**`docker compose` refuses to start: `POSTGRES_PASSWORD must be set`** — copy `.env.example` to `.env` and fill
in `POSTGRES_PASSWORD`, `SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD`.

**Backend restarts in a loop** — `docker compose logs backend`. Common causes: Postgres not healthy yet (the
`depends_on: condition: service_healthy` should prevent it), or a `DATABASE_URL` with the wrong driver (must be
`postgresql+psycopg://`, not `postgresql://`).

**Frontend loads but API calls 502** — nginx proxies to the host `backend:8000`; both services must be on the
same compose network. Check `docker compose ps`.

## Kubernetes

**Pods `ImagePullBackOff`** — the manifests reference `ghcr.io/example/...`. Build the images and retag, or
update `images:` in `kustomization.yaml`.

**HPA shows `<unknown>` targets** — install metrics-server (`kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`, plus `--kubelet-insecure-tls` on kind).

**`secret.example.yaml` was not applied** — intentional; it is excluded from kustomization so placeholders are
never deployed. Create the secret out-of-band (see the installation guide).

## Terraform

**`Error: No valid credential sources found`** — `plan` needs credentials even for a read-only data source
(`aws_ami`, `aws_availability_zones`). Configure a profile or use `AWS_PROFILE`.

**`terraform fmt -check` fails** — run `terraform fmt -recursive infrastructure/terraform`.

## Tests

**`pytest` cannot import `app`** — run from `backend/` with `PYTHONPATH=.`.

**Tests fail with a locked database on Windows** — a previous run left the SQLite file open. The suite uses a
temp file and recreates it; close stray Python processes and re-run.

**Frontend build passes locally but fails in CI** — CI uses `npm ci` with the committed lockfile. If you changed
dependencies, run `npm install` and commit `package-lock.json`.
