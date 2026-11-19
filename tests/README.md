# Tests

Two layers, deliberately separated by what they need.

## 1. Backend unit / API tests — `backend/tests/` (59 tests)

Self-contained: they create a temporary SQLite database, disable the scheduler and exercise the FastAPI app
through `TestClient`. No running server, no network, no AWS.

```bash
cd backend
PYTHONPATH=. pytest            # or: pytest -q
```

| File | Covers |
| --- | --- |
| `test_auth.py` | health, protected routes, bad credentials, role enforcement, user creation/duplicates |
| `test_monitoring.py` | inventory provenance, instance detail, metric ordering, collection cycle, spike → critical alert, threshold validation, summary shape |
| `test_security.py` | finding provenance labels, open SSH/RDP detection, scan tool outcomes, unavailable-tool honesty, JSON/CSV downloads, status updates, risk score |
| `test_logs_and_costs.py` | severity classification (incl. OOM escalation), search filters, fingerprint grouping, rule-based fallback, cost estimate labelling, recommendations, admin-only budget, negative pricing rejection |
| `test_incidents_remediation.py` | full lifecycle + illegal transitions + resolution summary requirement, notes, stats, allowlist, dry-run, four-eyes approval, execute-before-approve, rule validation |
| `test_hardening.py` | Strict request validation (unknown field → 422, wrong type → 422 not 500), CloudWatch numeric ids, incident reopen translation, `/api/v1/health` alias |
| `test_platform.py` | dashboard aggregation, AWS honesty, pipeline discovery, deployment ingest, audit trail, notifications, secret masking, simulated-only power actions |

## 2. Live API integration check — `tests/integration/live_api_check.py`

Requires a running server and exercises real subprocess scanners. It writes to the target database (one
incident, two remediation actions), so point it at development only.

```bash
# with the API running on :8000
python tests/integration/live_api_check.py --base-url http://127.0.0.1:8000

# custom account
python tests/integration/live_api_check.py --email engineer@cloudops.local --password '...'
```

Prints a PASS/FAIL line per assertion and exits non-zero on failure.

### Endpoint sweep — `tests/integration/endpoint_sweep.py`

Calls every route, including negative cases (bad types, unknown ids, illegal transitions), and fails if any
response is a 5xx or an unexpected status. Useful after changing schemas or adding routes.

```bash
python tests/integration/endpoint_sweep.py --base-url http://127.0.0.1:8000
```

## 3. Frontend

There is no component test suite; the frontend is verified by a strict TypeScript production build
(`npm run build`) and by the Playwright screenshot pass in `scripts/capture-screenshots.mjs`, which records
console errors per page (`screenshots/manifest.json`). Adding Vitest + Testing Library is the natural next step.

## What is intentionally not tested

* Real AWS calls (no account, and tests must not require one).
* Real remediation effects (nothing is executed; simulation only).
* Load/performance characteristics.

## CI

`.github/workflows/ci.yml` runs lint, this pytest suite and the frontend build on every push and pull request.
The live integration script is not run in CI because it needs a booted server; it is a local/pre-release check.
