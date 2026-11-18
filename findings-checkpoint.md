# CloudOps Sentinel smoke test — checkpoint

Tab: tab-iab-1 (built-in browser), base http://localhost:5173

## Completed
- Login OK (admin@cloudops.local) -> landed on /
- / Overview: rendered (KPIs, charts, tables), no error text, 0 console errors
- /instances: rendered (9-row table), 0 console errors
- /instances/7 (clicked first instance name "dev-bastion"): detail page rendered, chart present (13 svg), 0 console errors
- /monitoring: rendered, 0 console errors
- /security: rendered; header "Run scan" opened "Run a security scan" panel; "Start scan" produced result panel "Scan 436351c196584877 · 0 created, 10 updated, 0 resolved" with tool rows: sentinel-iac-rules executed 0 findings/0ms, aws-config-audit executed 9 findings/0ms, bandit executed 1 findings/3843ms; 0 console errors
- /costs: rendered, 0 console errors
- /logs: rendered, 0 console errors ("500" hit is benign text "batches of up to 500 records")
- /incidents: rendered, 0 console errors
- /remediation: rendered, 0 console errors
- /pipelines: rendered, 0 console errors
- /aws: rendered, 0 console errors

## Remaining
- /audit, /settings route checks + console errors
- Theme toggle (sun/moon) test + background colour comparison
- Screenshots (blocked: browser_screenshot "Browser operation deadline exceeded"/"timed out after 120000ms" on 3 attempts, 2 pages; printToPDF unavailable)

## Observations
- document.title stuck on "Sign in · CloudOps Sentinel" while on / (after login); other routes show generic "CloudOps Sentinel" (no per-route titles)
- Security scan result panel listed only 3 of 6 selected scanners (pip-audit, checkov, trivy unused; trivy is "not installed")

Files: routecheck.js (DOM check script), shots/ (no images saved)

## Final
- /audit: rendered, 0 console errors
- /settings: rendered, 0 console errors
- Theme toggle: body bg rgb(241,245,249) -> rgb(2,6,23), html class='dark', localStorage theme=dark (works)
- Screenshots: BLOCKED (5 attempts, 3 pages: 'Browser operation deadline exceeded' / 'timed out after 120000ms'); printToPDF unsupported ('Page.printToPDF' wasn't found)
- All 12 routes + instance detail + security scan completed. No console errors on any route.
