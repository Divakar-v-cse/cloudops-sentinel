#!/usr/bin/env bash
# Inject demo activity: logs, a metric spike, a security scan and an incident.
# Requires the API to be running. All generated data is clearly synthetic.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
EMAIL="${EMAIL:-admin@cloudops.local}"
PASSWORD="${PASSWORD:-Admin@12345}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

login() {
  curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
}

TOKEN="$(login | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
AUTH=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')

echo "→ ingesting sample logs"
curl -fsS -X POST "$BASE_URL/api/v1/logs" "${AUTH[@]}" -d @"$HERE/sample-logs.json" | head -c 300; echo

echo "→ running security scan (rules + aws + bandit)"
curl -fsS -X POST "$BASE_URL/api/v1/security/scan" "${AUTH[@]}" \
  -d '{"tools":["rules","aws","bandit"],"include_cloud":true}' \
  | python -c 'import json,sys; d=json.load(sys.stdin); print("scan", d["scan_id"], [(t["tool"], t["status"], t["findings"]) for t in d["tools"]])'

INSTANCE_ID="$(curl -fsS "$BASE_URL/api/v1/instances?source=simulated" -H "Authorization: Bearer $TOKEN" \
  | python -c 'import json,sys; rows=json.load(sys.stdin); print(next(r["id"] for r in rows if r["status"]=="running"))')"

echo "→ injecting CPU spike on instance $INSTANCE_ID"
curl -fsS -X POST "$BASE_URL/api/v1/monitoring/spike" "${AUTH[@]}" \
  -d "{\"instance_id\":$INSTANCE_ID,\"metric\":\"cpu_percent\",\"value\":97.5,\"minutes\":3}" | head -c 200; echo

echo "→ collecting telemetry"
curl -fsS -X POST "$BASE_URL/api/v1/monitoring/collect" "${AUTH[@]}" | head -c 200; echo

echo "→ opening a demo incident"
curl -fsS -X POST "$BASE_URL/api/v1/incidents" "${AUTH[@]}" \
  -d '{"title":"Demo: elevated latency on checkout-api","description":"Created by demo/seed-demo.sh","severity":"high","service":"checkout-api","detected_by":"manual"}' \
  | python -c 'import json,sys; d=json.load(sys.stdin); print(d["incident_number"], d["status"])'

echo "→ analysing order-worker logs"
curl -fsS -X POST "$BASE_URL/api/v1/logs/analyze" "${AUTH[@]}" \
  -d '{"service":"order-worker","hours":24}' \
  | python -c 'import json,sys; d=json.load(sys.stdin); print(d["source"], "|", d["summary"][:160])'

echo "Done. Refresh the UI — new logs, alerts, findings and an incident are visible."
