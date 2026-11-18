# Jenkins pipeline

The pipeline definition is the `Jenkinsfile` at the repository root (standard Jenkins convention).

## Job configuration

* **Type:** Pipeline → "Pipeline script from SCM"
* **SCM:** this repository, branch `*/main`
* **Script path:** `Jenkinsfile`
* **Parameters:** `ENVIRONMENT` (staging/production), `RUN_SECURITY_SCAN`, `SKIP_TESTS`

## Credentials to create (Manage Jenkins → Credentials)

| ID | Kind | Used for |
| --- | --- | --- |
| `kubeconfig-sentinel` | Secret file | `KUBECONFIG` for `kubectl` |
| `registry-sentinel` | Username with password | `docker login` / push |
| `sentinel-health-url` | Secret text | Post-deploy smoke test |

Create a group `cloudops-admins` and list the humans allowed to approve production. The `input` step submits to
that group only, with a 30-minute timeout.

## Stages

`Checkout → Backend build → Lint → Test (JUnit) → Frontend build → Docker image creation → Security scan →
Terraform validate → Approval (production only) → Deploy → Smoke test`

* Tests run with `DATABASE_URL=sqlite:///./jenkins.db` and `ENABLE_SCHEDULER=false`, so no external services are
  required on the agent.
* The security stage runs Trivy via the official container image plus Bandit and pip-audit from the venv.
* Findings are reported but do not fail the build; the release decision is the human approval gate.
* `post { always { archiveArtifacts ...; cleanWs() } }` keeps the workspace clean between runs.

## Agent requirements

Docker (with socket access for Trivy), Python 3.12, Node 20+, Terraform 1.6+, `kubectl`, and network access to
the registry and cluster. A `docker` label agent is a reasonable default.
