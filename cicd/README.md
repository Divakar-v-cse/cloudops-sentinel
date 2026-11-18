# CI/CD

Two pipelines are provided. Both are real configuration files that have been syntax-checked; neither has been
executed on GitHub/Jenkins infrastructure from this environment, so treat their first run as the validation.

| Pipeline | File | Trigger | Stages |
| --- | --- | --- | --- |
| GitHub Actions — CI | `.github/workflows/ci.yml` | push/PR to `main`/`develop`, manual | backend lint + tests, frontend build, dependency/code scan, Docker build + Trivy, Terraform fmt/validate, compose + manifest validation |
| GitHub Actions — Release | `.github/workflows/release.yml` | tag `v*.*.*`, manual | build & push to GHCR, deploy staging, **manual approval** → deploy production, smoke test `/health` |
| Jenkins | `Jenkinsfile` (repo root) | SCM | checkout, build, lint, test (JUnit), frontend build, Docker image, security scan, Terraform validate, **input approval** for production, deploy, smoke test |

## Why the workflows live in `.github/workflows`

GitHub only executes workflow files from `.github/workflows`. Keeping a second copy under `cicd/` would drift
from the executed definition, so this directory documents and supports the pipelines instead of duplicating them:

```
cicd/
  README.md              this file
  github-actions/README.md   what each workflow does, secrets required, how to trigger
  jenkins/README.md          credentials, agents, approval configuration
```

## Repository secrets used by the workflows

| Secret | Used by | Purpose |
| --- | --- | --- |
| `GITHUB_TOKEN` | release | push images to GHCR (automatic, no setup) |
| `KUBE_CONFIG_STAGING` | release | base64 kubeconfig for staging |
| `KUBE_CONFIG_PRODUCTION` | release | base64 kubeconfig for production |
| `PRODUCTION_HEALTH_URL` | release | smoke-test URL |
| `kubeconfig-sentinel` (Jenkins credential) | Jenkinsfile | deploy target |
| `registry-sentinel` (username/password) | Jenkinsfile | container registry push |
| `sentinel-health-url` (secret text) | Jenkinsfile | smoke test |

No secret is printed: GitHub masks secret values, and the Jenkinsfile injects credentials with
`withCredentials` only at the point of use.

## Approval gates

* GitHub: create an Environment named `production` with required reviewers. The `deploy-production` job targets
  it, so the job pauses until a reviewer approves.
* Jenkins: `input` step restricted to the `cloudops-admins` group, with a 30-minute timeout.

## Local equivalents

```bash
# what CI runs
ruff check backend/app backend/tests
cd backend && PYTHONPATH=. pytest
cd frontend && npm run build
terraform -chdir=infrastructure/terraform fmt -check -recursive
terraform -chdir=infrastructure/terraform init -backend=false && terraform -chdir=infrastructure/terraform validate
docker compose config --quiet
kubectl kustomize infrastructure/kubernetes > /dev/null

# security
bash scripts/security-scan.sh
```
