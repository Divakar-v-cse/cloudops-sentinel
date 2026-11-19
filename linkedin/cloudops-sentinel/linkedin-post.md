# CloudOps Sentinel — LinkedIn post 1

> Post type: **document post** using `carousels/cloudops-sentinel.pdf` (8 slides).
> Cover image: `covers/cloudops-sentinel.png`. Diagram asset: `diagrams/cloudops-sentinel.png`.

---

Most cloud dashboards tell you something is wrong. Very few let you fix it safely.

What kept going wrong:
• Ops teams juggle separate tools for metrics, security posture, spend, logs and incidents.
• Alerting is noisy but remediation is manual, slow and risky.
• Most dashboards are mockups: they show numbers but cannot act on them.

So I built CloudOps Sentinel — AI-assisted cloud operations, security and human-approved remediation.

One operations console where monitoring, AWS inventory, security scanning, cost analysis, log intelligence and incident response share a single data model — and remediation is gated behind dry-run plus a second human approval.

What it actually does:
→ Real host telemetry from psutil, with a clearly labelled simulated fleet for demos
→ Read-only AWS integration; no credential ever leaves the environment
→ Allowlisted remediation actions only, all audited

How it works, end to end:
Dashboard → REST API → service layer → PostgreSQL; optional boto3 read-only calls to AWS; scheduler collects metrics every 15–30s and evaluates thresholds.

Stack: Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL · React · TypeScript · Terraform · Docker · AWS

The parts that took the longest:
• Provenance is a product feature: users must always know if a number is real or simulated
• Validation belongs at the edge — untyped dict bodies turn typos into silent no-ops

Evidence it works:
• 59 backend tests and 96-endpoint sweep passing
• CI green across 6 jobs including Docker build and Trivy
• 0 dependency vulnerabilities after remediation (44 packages audited)

Architecture, screenshots and the full source are in the repository:
https://github.com/Divakar-v-cse/cloudops-sentinel

Built to answer one question: what would a cloud operations console look like if it had to be trusted in production?

If you are working on something similar — or you would review the architecture and tell me what you would change — I would genuinely like to hear it.

#CloudEngineering #DevOps #SRE #Observability #FastAPI #CloudSecurity
