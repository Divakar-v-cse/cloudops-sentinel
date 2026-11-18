# Resume-ready project description

## Short form (2 lines, for a project list)

**CloudOps Sentinel — AI-Assisted Cloud Operations Platform** · [github.com/Divakar-v-cse/cloudops-sentinel](https://github.com/Divakar-v-cse/cloudops-sentinel)
`Python 3.12` `FastAPI` `SQLAlchemy` `PostgreSQL` `React` `TypeScript` `AWS` `Docker` `Terraform` `GitHub Actions`
Built a full-stack AWS operations platform (17-table schema, 80+ REST endpoints, 14-page React console) with real
psutil host telemetry, read-only boto3 inventory, security scanning (Bandit/pip-audit/Checkov/Trivy), cost
optimisation, log intelligence and dry-run-first, human-approved remediation; 45 backend tests, CI/CD and IaC.

## Bullet points (pick 4–6 for a resume)

* Designed and shipped **CloudOps Sentinel**, a FastAPI + React platform that unifies infrastructure monitoring,
  security posture, cloud cost analysis, log intelligence, incident response and remediation in one control plane.
* Implemented a **monitoring engine** that samples real host CPU/memory/disk/network via `psutil`, classifies
  health against configurable thresholds, and auto-opens deduplicated incidents from sustained critical breaches.
* Built an **optional read-only AWS integration** (`boto3`) for EC2, S3, IAM, security groups and CloudWatch with
  least-privilege IAM, graceful credential degradation and explicit real-vs-simulated data provenance.
* Created a **security scanning pipeline** that executes Bandit, pip-audit, Checkov and Trivy as isolated
  subprocesses, normalises findings into one schema with evidence and remediation guidance, and exports JSON/CSV
  reports — reporting unavailable tools honestly instead of fabricating results.
* Engineered a **safe remediation engine**: allowlisted actions, dry-run by default, health checks before/after,
  four-eyes approval (requester cannot approve), full audit trail, and no destructive cloud API implemented.
* Delivered a **14-page TypeScript dashboard** with dark/light themes, typed API client, loading/empty/error
  states, and Recharts visualisations backed by live endpoints — zero placeholder buttons.
* Established **CI/CD and IaC**: GitHub Actions (lint, 45 tests, frontend build, dependency and image scanning,
  Terraform validation), Jenkins pipeline with approval gate, multi-stage Dockerfiles, Compose stack, Kubernetes
  manifests with probes and HPAs, and Terraform for VPC/S3/IAM/CloudWatch.

## ATS-friendly paragraph

CloudOps Sentinel is a cloud operations and auto-remediation platform built with Python 3.12, FastAPI,
SQLAlchemy, PostgreSQL and a React/TypeScript frontend. It provides infrastructure monitoring with psutil and
Boto3, CloudWatch integration, configurable alerting and incident management, anomaly and idle-resource
detection for cloud cost optimisation, log analysis with a deterministic rule-based fallback, a multi-tool
security scanner (Trivy, Checkov, Bandit, pip-audit), and a remediation workflow with dry-run defaults and
mandatory human approval. The system is containerised with Docker and Docker Compose, deployable to Kubernetes,
provisioned with Terraform, and validated by GitHub Actions CI with 45 automated tests, plus Jenkins with a
manual production gate.

## Skills this project evidences

`Python` `FastAPI` `Pydantic` `SQLAlchemy` `Alembic` `PostgreSQL` `SQLite` `pytest` `React` `TypeScript` `Vite`
`Tailwind CSS` `Recharts` `AWS EC2/S3/IAM/VPC/CloudWatch` `boto3` `Linux` `Bash` `Docker` `Kubernetes`
`Terraform` `GitHub Actions` `Jenkins` `Trivy` `Checkov` `Bandit` `pip-audit` `JWT` `RBAC` `observability`
`incident response` `cost optimisation` `least privilege` `secure SDLC`

## Talking point that usually lands

> The hardest part was not the features — it was making the platform honest. It can run with no AWS account, so
> I made provenance a first-class schema concern and wrote tests that fail if simulated data is ever presented
> as real, or if a scanner that did not run reports findings.
