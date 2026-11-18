# GitHub Actions workflows

Canonical files live in `.github/workflows/` because GitHub only reads that path. This page explains them.

## `ci.yml` — continuous integration

Triggers: push and pull request to `main`/`develop`, plus manual dispatch. Concurrency cancels superseded runs
on the same ref.

| Job | What it proves |
| --- | --- |
| `backend-quality` | `ruff check` passes; 45 pytest tests pass against SQLite with the scheduler disabled |
| `frontend-build` | `npm ci` from the lockfile, TypeScript build (`tsc -b`) and Vite production bundle succeed |
| `dependency-scan` | `pip-audit` and `bandit` produce reports as build artifacts (non-blocking, so a new advisory does not block unrelated PRs) |
| `container-build` | Both Dockerfiles build; Trivy scans the backend image and fails the job on CRITICAL filesystem findings |
| `terraform-check` | `terraform fmt -check -recursive` and `terraform validate` with providers installed but no backend |
| `compose-validate` | `docker compose config` accepts the stack with placeholder secrets; kubeconform validates every manifest |

Artifacts: `ci-database` on failure, `frontend-dist`, `security-reports`.

## `release.yml` — build and deploy

Triggered by a `v*.*.*` tag or manual dispatch with a version input.

1. Builds both images and pushes `:<version>` and `:latest` to GHCR.
2. Deploys to the `staging` environment and waits for rollout.
3. Deploys to `production`, which is gated by the environment's required reviewers.
4. Smoke-tests `${{ secrets.PRODUCTION_HEALTH_URL }}` for `"status":"ok"`.

## Enabling it in a fork

1. Settings → Actions → General → allow workflows.
2. Create environments `staging` and `production`; add reviewers to `production`.
3. Add the secrets listed in `cicd/README.md`.
4. Push a tag: `git tag v1.0.0 && git push origin v1.0.0`.

## Notes

* Images are pushed as `<owner>/<repo>-backend` and `<owner>/<repo>-frontend`.
* The Trivy filesystem scan fails only on CRITICAL findings with a fix available (`ignore-unfixed: true`), which
  keeps the signal actionable.
* `terraform-check` needs no AWS credentials; `validate` is offline. A `plan` would require credentials and is
  deliberately not part of CI.
