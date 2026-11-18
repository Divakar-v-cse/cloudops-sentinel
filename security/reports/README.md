# Scan reports

Reports in this folder are produced by `scripts/security-scan.sh` and committed deliberately so the repository's
security posture is auditable over time.

Naming: `security-scan-YYYY-MM-DD.md` (summary) alongside raw `.json` output from each scanner where available.

Each report states:

* the exact command run,
* the tool version,
* the number of findings by severity,
* accepted exceptions with justification,
* what was **not** scanned (so absence of findings is never mistaken for proof of safety).

Do not edit a report after committing it. Add a new dated report instead.
