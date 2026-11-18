# Security scan report — 2026-11-18

Repository: `cloudops-sentinel` · Branch `main` · Environment: Windows 11, Python 3.12.2
Scanned commit: working tree at time of scan (pre-push). Raw artefacts: `bandit.json`, `pip-audit.json` in this folder.

## Summary

| Scanner | Version | Scope | Findings | Critical | High | Medium | Low |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bandit | 1.8.0 | `backend/app`, 7,283 LOC | 18 | 0 | **0** | 0 | 18 |
| pip-audit | 2.7.3 | `backend/requirements.txt`, 44 packages | **0** | — | 0 | 0 | — |
| Trivy | — | filesystem / images | **not run** — binary not installed | — | — | — | — |
| Checkov | — | Terraform / Kubernetes | **not run** — not installed | — | — | — | — |

Commands:

```bash
bandit -r backend/app -c security/.bandit -f json -o security/reports/bandit.json
pip-audit -r backend/requirements.txt -f json -o security/reports/pip-audit.json
```

## 1. Remediated during this scan

### 1.1 HIGH — weak hash for a security purpose (B324)

```
>> Issue: [B324:hashlib] Use of weak SHA1 hash for security.
   Severity: High   Confidence: High
   Location: backend/app/services/logs.py:69
```

**Was:** `hashlib.sha1(...)` used to derive the log-grouping fingerprint. Though the value is only a grouping
key, Bandit correctly flags an unqualified SHA-1 call because it cannot know the intent.

**Fix applied:** the call now declares intent explicitly:

```python
# SHA-1 is used only as a stable grouping key for log lines, never for
# authentication or integrity, hence usedforsecurity=False.
return hashlib.sha1(
    f"{service}:{normalise_message(message)}".encode("utf-8"), usedforsecurity=False
).hexdigest()[:16]
```

**Verified:** re-scan reports 0 HIGH, 0 MEDIUM. The 45-test suite still passes.

### 1.2 Dependency advisories — 30 vulnerabilities in 3 packages → 0

Initial `pip-audit` result:

| Package | Installed | Advisories | Fixed in (per advisory) |
| --- | --- | --- | --- |
| `python-multipart` | 0.0.20 | 6 (PYSEC-2026-1852, -3036…-3040) | 0.0.22 … 0.0.31 |
| `PyJWT` | 2.10.1 | 17 (PYSEC-2025-183, PYSEC-2026-120/175-179/4140-4149/4183, GHSA-pxh4-856f-4h89) | 2.12.0 … 2.15.0 |
| `starlette` | 0.41.3 | 7 (PYSEC-2026-161/248/249/1941/1942/2280/2281) | 0.47.2 … 1.3.1 |

Upgraded and pinned to the versions that clear every advisory:

```text
fastapi==0.163.2
starlette==1.10.0
python-multipart==0.0.34
PyJWT==2.15.1
```

**Verified after upgrade:** `pip-audit` → *"No known vulnerabilities found"* (44 packages); `pytest` → 45 passed;
`ruff check` → all checks passed. The application's auth, upload-form and response paths were exercised by the
test suite on the new versions.

## 2. Accepted low-severity findings (18)

| Rule | Count | Location | Assessment |
| --- | --- | --- | --- |
| B311 `random` | 16 | `services/monitoring.py` (9), `services/bootstrap.py` (7) | Pseudo-randomness is used **only** to synthesise demo telemetry and seed demo records. No token, password, salt or key is generated with `random`. Cryptographic material uses `os.urandom` (`core/security.py`) and JWT signing. Accepted as non-exploitable in this context. |
| B404 `subprocess` import | 1 | `services/security_scan.py:19` | Required to execute Bandit/pip-audit/Checkov/Trivy. No user-supplied command or shell string reaches these calls. |
| B603 `subprocess` call | 1 | `services/security_scan.py:59` | Arguments are a fixed list built from constants plus `sys.executable`; `shell=False` (default); targets are repository paths. The scanner allowlist (`TOOL_RUNNERS`) prevents arbitrary tool selection. |

These are documented rather than suppressed. `B105` (hardcoded password string) is skipped in
`security/.bandit` because `core/config.py` intentionally ships environment-overridable development
placeholders; the runtime reports them at startup via `settings.insecure_defaults`, and
`GET /api/v1/settings/runtime` exposes the warning.

## 3. Not scanned — stated explicitly

* **Container images.** No image was built during this scan, so no image vulnerability report exists. Run
  `trivy image --severity CRITICAL,HIGH cloudops-sentinel-backend:local` after `docker build`.
* **Trivy filesystem/IaC/secret scan.** Binary absent in this environment (`trivy` reports `skipped` inside the
  product too). `security/trivy.yaml` and `security/trivy-secret.yaml` are ready for CI.
* **Checkov.** Not installed. `infrastructure/terraform` was validated with `terraform fmt -check` and
  `terraform validate` (both pass) but not policy-scanned in this run.
* **AWS account posture.** No AWS account is connected. All AWS findings shown in the product are derived from
  the simulated inventory and are labelled `simulated`. No claim is made about any real account.
* **Frontend dependency audit.** `npm audit` was not run in this pass; CI runs Trivy on the built image.

## 4. Controls verified by inspection (not by this scan)

| Control | Evidence |
| --- | --- |
| No committed secrets | `.gitignore` covers `.env`, `*.pem`, `*.key`, Terraform state and lock-provider dirs; only `.env.example` with placeholders is tracked |
| Password hashing | PBKDF2-HMAC-SHA256, 390,000 iterations, 16-byte per-user salt (`core/security.py`) |
| Token validation | PyJWT HS256 with `exp` required and explicit algorithm allowlist |
| Authorisation | Role dependencies on every mutating route; admin-only settings/thresholds/budget/users |
| Destructive actions | Not implemented in `ACTION_REGISTRY`; unknown actions rejected with 422 |
| Self-approval | Blocked server-side (`requested_by == actor → 403`) |
| AWS mutation | No mutating AWS API call exists in the codebase |
| Secret exposure | `/settings/runtime` masks the DSN and never returns `SECRET_KEY` or `AI_API_KEY` |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP in nginx |

## 5. Reproduce

```bash
pip install bandit pip-audit
bandit -r backend/app -c security/.bandit -f screen
pip-audit -r backend/requirements.txt
# full wrapper incl. Trivy/Checkov when installed:
bash scripts/security-scan.sh
```

A future run must produce a **new dated report**; do not edit this file after commit.
