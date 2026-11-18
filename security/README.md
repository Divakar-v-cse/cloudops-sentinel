# Security tooling

This directory holds scanner configuration and the results of scans actually executed against this repository.
Nothing here is aspirational — every number in `reports/` came from a real run.

| File | Purpose |
| --- | --- |
| `.bandit` | Bandit config: scope, exclusions, documented exceptions |
| `trivy.yaml` | Trivy filesystem/image scan config (vuln + misconfig + secret) |
| `trivy-secret.yaml` | Custom secret-detection rules (AWS keys, PEM keys, JWTs) |
| `reports/` | Real scan output |

## How to run each scanner

```bash
# Bandit — Python static analysis
pip install bandit
bandit -r backend/app -c security/.bandit -f screen

# pip-audit — dependency advisories (needs network)
pip install pip-audit
pip-audit -r backend/requirements.txt

# Checkov — Terraform / Kubernetes policy
pip install checkov
checkov -d infrastructure/terraform --framework terraform
checkov -d infrastructure/kubernetes --framework kubernetes

# Trivy — filesystem (deps, IaC, secrets), then images
trivy fs --config security/trivy.yaml .
trivy image --severity CRITICAL,HIGH cloudops-sentinel-backend:local
trivy image --severity CRITICAL,HIGH cloudops-sentinel-frontend:local
```

Or run the wrapper, which records output into `security/reports/`:

```bash
bash scripts/security-scan.sh
```

## What the application does with these tools

The platform itself orchestrates Bandit, pip-audit, Checkov and Trivy from
`backend/app/services/security_scan.py`, normalises their JSON into one finding schema, and exposes the result in
the UI and via `/api/v1/security/report`. Tools that are not installed are reported as `skipped` with zero
findings — the platform never invents scanner output. This directory is for the **repository's own** security
posture, which is a separate concern from scanning the user's AWS account.

## Reporting a vulnerability

Open a private security advisory on the repository rather than a public issue. Do not include exploit details in
a public issue.
