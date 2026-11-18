#!/usr/bin/env bash
# Run the repository's own security scanners and record the output.
# Usage: bash scripts/security-scan.sh [output-dir]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/security/reports}"
STAMP="$(date +%Y-%m-%d)"
mkdir -p "$OUT"

cd "$ROOT" || exit 1

echo "== Bandit =="
if command -v bandit >/dev/null 2>&1; then
  bandit -r backend/app -c security/.bandit -f json -o "$OUT/bandit-$STAMP.json" 2>/dev/null
  bandit -r backend/app -c security/.bandit -f screen 2>/dev/null | tail -n 25
else
  echo "bandit not installed — skipped"
fi

echo "== pip-audit =="
if command -v pip-audit >/dev/null 2>&1; then
  pip-audit -r backend/requirements.txt -f json -o "$OUT/pip-audit-$STAMP.json" 2>&1 | tail -n 5
else
  echo "pip-audit not installed — skipped"
fi

echo "== Checkov (Terraform) =="
if command -v checkov >/dev/null 2>&1; then
  checkov -d infrastructure/terraform --framework terraform --compact --quiet \
    -o json > "$OUT/checkov-terraform-$STAMP.json" 2>/dev/null
  echo "written to $OUT/checkov-terraform-$STAMP.json"
else
  echo "checkov not installed — skipped"
fi

echo "== Trivy =="
if command -v trivy >/dev/null 2>&1; then
  trivy fs --config security/trivy.yaml --format json -o "$OUT/trivy-fs-$STAMP.json" . 2>/dev/null
  trivy fs --config security/trivy.yaml --format table . 2>/dev/null | tail -n 30
else
  echo "trivy not installed — skipped"
fi

echo
echo "Scan artefacts written to $OUT"
echo "Summarise them in $OUT/security-scan-$STAMP.md (template: $OUT/README.md)."
