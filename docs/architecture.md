# Architecture

CloudOps Sentinel is a three-tier platform: a React operations console, a FastAPI service layer that owns all
business logic, and a relational store that also acts as the audit system of record. Cloud access is optional and
strictly read-only.

## 1. Component diagram

```mermaid
flowchart TB
    subgraph Client["Browser"]
        UI["React 18 + TypeScript<br/>Vite · Tailwind · Recharts · React Router"]
    end

    subgraph API["FastAPI service (Python 3.12)"]
        direction TB
        ROUTES["API routes (/api/v1)<br/>auth · instances · monitoring · security<br/>costs · logs · incidents · remediation<br/>deployments · aws · audit · settings"]
        DEPS["deps.py<br/>JWT auth · RBAC dependencies · DB session"]
        subgraph SVC["Service layer (business logic)"]
            MON["monitoring<br/>psutil collector + simulator<br/>health classification · alerting"]
            SEC["security_scan<br/>tool orchestration · policy rules<br/>report export"]
            COST["cost<br/>pricing model · idle detection<br/>recommendations"]
            LOG["logs<br/>fingerprinting · severity<br/>AI / rule-based analysis"]
            INC["incidents<br/>state machine · timeline"]
            REM["remediation<br/>allowlist · dry-run · approvals"]
            DEP["deployments<br/>pipeline discovery · history"]
            DASH["dashboard<br/>cross-module aggregation"]
        end
        JOBS["Lifespan scheduler<br/>collect → evaluate rules → prune"]
    end

    subgraph Data["Persistence"]
        DB[("PostgreSQL 16<br/>or SQLite (local)")]
        AUD[("audit_logs<br/>append-only")]
    end

    subgraph External["Optional / read-only"]
        AWS["AWS APIs (boto3)<br/>EC2 · S3 · IAM · CloudWatch · STS"]
        TOOLS["Bandit · pip-audit<br/>Checkov · Trivy"]
        LLM["OpenAI-compatible LLM<br/>optional"]
        HOST["Local host metrics<br/>(psutil)"]
    end

    UI -->|"HTTPS + JWT bearer"| ROUTES
    ROUTES --> DEPS --> SVC
    SVC --> DB
    SVC --> AUD
    JOBS --> MON
    JOBS --> REM
    MON --> HOST
    MON --> DB
    SEC --> TOOLS
    SEC --> AWS
    LOG --> LLM
    COST --> DB
    DEP --> DB
    DASH --> DB
```

## 2. Request flow

```mermaid
sequenceDiagram
    participant U as Operator
    participant UI as React UI
    participant A as FastAPI route
    participant D as deps.py
    participant S as Service
    participant DB as Database

    U->>UI: Click "Run scan"
    UI->>A: POST /api/v1/security/scan (Bearer JWT)
    A->>D: get_current_user + require_operator
    D-->>A: User(role=engineer)
    A->>S: security_scan.run_scan(tools, actor)
    S->>S: execute scanners (subprocess, JSON parse)
    S->>DB: upsert findings + audit entry
    S-->>A: ScanResult(tools[], counts)
    A-->>UI: 200 JSON
    UI-->>U: per-tool outcome + new findings
```

## 3. Monitoring data flow

1. The lifespan scheduler wakes every `MONITORING_INTERVAL_SECONDS` (default 15s).
2. `collect_local_snapshot` samples the real host with psutil (CPU, virtual memory, disk usage, network
   counters converted to kbit/s using the delta since the previous sample, uptime, process count).
3. `simulate_all` produces synthetic samples for inventory rows marked `source='simulated'`, using a workload
   profile (`web`, `api`, `worker`, `database`, `cache`, `bastion`), a daily sine curve, bounded noise and an
   optional operator-injected spike.
4. Each row is persisted to `metrics` with its `source`, then `evaluate_thresholds` compares the sample with the
   `thresholds` table. Breaches create notifications (rate-limited per instance/signal/level for 10 minutes) and,
   for critical breaches, a deduplicated incident.
5. `prune_history` deletes samples older than `MONITORING_HISTORY_RETENTION_HOURS`.
6. `evaluate_rules` checks remediation rules against the recent sample window and creates dry-run or
   approval-pending actions.

## 4. Data provenance contract

Every record that can be synthetic carries its origin. This is enforced in the schema, not just the UI.

| Entity | Field | Values |
| --- | --- | --- |
| Instance | `source` | `local`, `simulated`, `aws` |
| Metric | `source` | `local`, `simulated` |
| SecurityFinding | `source_kind` + `scan_source` | `aws`, `simulated`, `tool`, `rule-engine` |
| CostRecord | `source` | `simulated`, `estimated`, `aws` |
| Deployment | `source` | `simulated`, `pipeline` |
| LogAnalysis | `source` | `ai`, `rule-based` |

Rules that follow from this:

* A simulated instance can never be presented as a real server; the API and UI label it.
* AWS inventory is only `source=aws` when a boto3 call actually returned it.
* A scanner that is not installed produces a `skipped` status with zero findings — never invented findings.
* Cost figures are `estimated` unless imported from a billing source.

## 5. Clean-architecture boundaries

* **Routes** validate input, authorise, and delegate. No SQL, no business rules.
* **Services** own logic and are importable without FastAPI (used by the scheduler and tests).
* **Models** are persistence only; Pydantic schemas define the wire contract.
* **Cross-cutting concerns** (audit, notifications, settings) are services, not middleware, so background
  work can reuse them.

Dependency direction is one-way: `api → services → models`, with `core` available to all layers. Services never
import routes.

## 6. Deployment topologies

| Mode | Components | Notes |
| --- | --- | --- |
| Local (default) | uvicorn + Vite dev server + SQLite | Zero external dependencies, no cost |
| Container | compose: nginx frontend, uvicorn backend, PostgreSQL 16, optional Redis | `docker compose up -d --build` |
| Kubernetes | Same images, StatefulSet Postgres, 2×2 Deployments, probes, HPAs | kind/minikube is enough; no paid cluster required |
| AWS | Optional read-only role + EC2/S3/CloudWatch via Terraform | `instance_count` defaults to 0 so a plan is free |

## 7. Failure behaviour

* AWS unreachable or uncredentialled → mode `not_configured`, cloud panels show simulated data, the rest of the
  platform is unaffected.
* Scanner missing → `skipped` status surfaced in the scan result.
* LLM unreachable → logged warning and deterministic rule-based analysis (the response's `source` field says so).
* Scheduler exception → logged, exponential backoff capped at 5 minutes; the API keeps serving.
* Database unavailable → `/health` returns `degraded` and reports the error.
