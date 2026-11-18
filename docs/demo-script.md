# Demo video — recording script and instructions

Target length: **4–6 minutes**. No editing required; a single continuous take is fine if you follow the beats.

> Recording status: a video was **not** produced in this environment (no screen recorder, and the browser
> automation available here could not capture frames reliably). This document is the complete script plus
> exact recording instructions so you can produce it in one pass.

## 1. Preparation (5 minutes before recording)

```bash
# terminal 1 — API
cd backend && PYTHONPATH=. uvicorn app.main:app --port 8000

# terminal 2 — UI
cd frontend && npm run dev
```

Checklist:

- [ ] Browser zoom 100%, window 1600×900 or larger.
- [ ] Sign in once to warm the caches, then sign out so the login shot is clean.
- [ ] Decide the theme: **dark** looks best on video.
- [ ] Close other tabs, Slack/Teams notifications, and any personal bookmarks.
- [ ] Have the admin credentials ready: `admin@cloudops.local` / your `DEFAULT_ADMIN_PASSWORD`.
- [ ] Optional: `docker compose up -d` if you want to show the container path in a B-roll shot.

## 2. Shot list with narration

| # | Screen / action | Say (near-verbatim) | Duration |
| --- | --- | --- | --- |
| 1 | Login page | "CloudOps Sentinel is a cloud operations platform: monitoring, security, cost, logs, incidents and remediation in one place. It runs fully locally — no AWS account required." | 15s |
| 2 | Sign in → Overview | "After login the overview aggregates every module from live APIs. Note the provenance line: one host is measured with psutil, eight are labelled simulated." | 25s |
| 3 | Point at KPI cards, then the fleet chart | "Health, critical incidents, security risk, estimated spend, deployment state — all computed from the database, not hardcoded." | 15s |
| 4 | Infrastructure | "Inventory shows the data source on every row. The local host is real telemetry; simulated rows are synthetic and never presented as real servers." | 20s |
| 5 | Open `prod-api-01` | "Detail view: metadata, current utilisation, threshold breaches, and six hours of history." | 20s |
| 6 | Monitoring → inject spike (CPU 97%, 3 min) → Collect now | "I'll inject a synthetic spike to prove the alerting path. Collection runs; the thresholds evaluate; the breach appears." | 25s |
| 7 | Alerts panel + Incidents page | "A critical breach auto-opens an incident, deduplicated per instance and signal. Here it is in the queue." | 20s |
| 8 | Open the incident → Acknowledge → Start investigation | "The lifecycle is enforced server-side: detected, acknowledged, investigating, resolved, closed. Illegal jumps are rejected with 409." | 25s |
| 9 | Security → Run scan (keep all tools) → result panel | "The scanner runs real tools. Bandit executed, AWS config audit ran against simulated inventory, Trivy is not installed so it reports skipped with zero findings — it never invents results." | 35s |
| 10 | Expand a finding | "Each finding carries severity, evidence, remediation guidance, scan source and timestamps. JSON and CSV export are real downloads." | 25s |
| 11 | Cost optimisation | "Estimates come from an editable pricing model, not a bill. Idle and oversized resources are detected from actual utilisation samples, with the evidence shown." | 30s |
| 12 | Logs → analyse the OOM group | "Log analysis groups by fingerprint. Without an LLM key it uses deterministic rules — and always states that a hypothesis is not a confirmed root cause." | 30s |
| 13 | Remediation → Request action → dry-run | "Remediation is safe by construction. Dry-run first: it returns a plan and explicitly says no change was made." | 25s |
| 14 | Submit a real action → pending approval → try to approve as requester | "A real action needs approval, and the requester cannot approve their own change — four eyes, enforced server-side." | 25s |
| 15 | Sign in as admin in a second window (or use an admin session) → Approve → Execute | "Approved, then executed. The output is prefixed SIMULATED: this build never calls a mutating cloud API." | 30s |
| 16 | Audit logs → filter `remediation.approved` | "Every decision is in the audit trail: who requested, who approved, what was executed." | 20s |
| 17 | Settings (optional) | "Runtime config, tool availability, retention and users. Secrets are never returned by the API." | 15s |
| 18 | Close | "FastAPI, React, PostgreSQL or SQLite, Docker, Kubernetes, Terraform and CI — built to be honest about its data and safe by default." | 10s |

## 3. Recording instructions

### Windows (built-in, zero install)

1. `Win + G` opens Xbox Game Bar → click **Record** (captures the active window).
2. Or `Win + Alt + R` to start/stop immediately.
3. Output lands in `Videos/Captures`.
4. Record narration separately with Voice Recorder, or narrate live (Game Bar captures the mic if enabled in
   Settings → Capturing).

### OBS Studio (best quality, free)

1. Install OBS, add a **Display Capture** source, set canvas 1920×1080.
2. Settings → Output → Recording: MP4, 30 fps, quality "High".
3. Settings → Audio: enable the mic, add a noise-suppression filter.
4. Record, then optionally trim the head/tail in OBS's replay or any editor.

### macOS

`Cmd + Shift + 5` → **Record Selected Portion**, microphone → Built-in.

### Linux

GNOME: `Ctrl + Alt + Shift + R`. Or `ffmpeg -f x11grab -i :0.0 -f pulse -i default demo.mp4`.

## 4. If a step misbehaves on camera

* No alerts after injecting a spike → the spike is scoped to simulated instances; confirm you picked a
  simulated row, then press **Collect now** again (threshold evaluation runs on collection).
* Security scan takes >60s → it is running pip-audit against the network; either wait or deselect `pip-audit`.
* Empty charts → metrics need at least one collection cycle; press **Collect now** first.

## 5. Publishing

* Upload as **unlisted** to YouTube and link it from the README, or keep the MP4 in `demo/` (it is git-ignored;
  drop a link instead of committing a large binary).
* Update the repository's "Demo" section with the link and the date recorded.
