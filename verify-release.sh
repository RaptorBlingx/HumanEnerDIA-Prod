#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HUMANERDIA_BASE_URL="${HUMANERDIA_BASE_URL:-http://localhost:8080}"
ANALYTICS_BASE_URL="${ANALYTICS_BASE_URL:-http://localhost:8001}"
OVOS_BASE_URL="${OVOS_BASE_URL:-http://localhost:5000}"

pass() {
  printf '[OK] %s\n' "$1"
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -Eiq "$pattern" "$file"; then
    pass "$label"
  else
    echo "[FAIL] $label" >&2
    echo "Missing pattern: $pattern" >&2
    exit 1
  fi
}

command -v curl >/dev/null 2>&1 || { echo "Missing required command: curl" >&2; exit 1; }
command -v grep >/dev/null 2>&1 || { echo "Missing required command: grep" >&2; exit 1; }

echo "HumanEnerDIA verification"
echo "HumanEnerDIA: $HUMANERDIA_BASE_URL"
echo "Analytics:    $ANALYTICS_BASE_URL"
echo "OVOS:         $OVOS_BASE_URL (optional for EnMS-only)"
echo

if command -v docker >/dev/null 2>&1 && [[ -f docker-compose.yml ]]; then
  compose_files=(-f docker-compose.yml)
  [[ -f docker-compose.ovos.yml ]] && compose_files+=(-f docker-compose.ovos.yml)
  docker compose "${compose_files[@]}" config --quiet
  pass "Docker Compose config validates"
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

curl -fsSL --max-time 30 "$HUMANERDIA_BASE_URL/health" -o "$tmpdir/humanerdia-health.txt"
assert_contains "$tmpdir/humanerdia-health.txt" '^healthy$' "Nginx health endpoint"

curl -fsSL --max-time 30 "$ANALYTICS_BASE_URL/api/v1/health" -o "$tmpdir/analytics-health.json"
assert_contains "$tmpdir/analytics-health.json" '"status"[[:space:]]*:[[:space:]]*"healthy"' "Analytics health endpoint"

if curl -fsSL --max-time 30 "$OVOS_BASE_URL/health" -o "$tmpdir/ovos-health.json"; then
  assert_contains "$tmpdir/ovos-health.json" '"status"[[:space:]]*:[[:space:]]*"healthy"' "OVOS bridge health endpoint"
  assert_contains "$tmpdir/ovos-health.json" '"messagebus_connected"[[:space:]]*:[[:space:]]*true' "OVOS messagebus connection"

  curl -fsS --max-time 95 \
    -X POST "$OVOS_BASE_URL/query" \
    -H 'Content-Type: application/json' \
    -d '{"text":"what is the power of compressor one","session_id":"prod-deploy-verify"}' \
    -o "$tmpdir/ovos-query.json"
  assert_contains "$tmpdir/ovos-query.json" '"success"[[:space:]]*:[[:space:]]*true' "OVOS smoke query"
  assert_contains "$tmpdir/ovos-query.json" 'Compressor-1|compressor one|machine_status' "OVOS smoke query content"
else
  echo "[SKIP] OVOS bridge was not reachable at $OVOS_BASE_URL"
fi

echo
echo "Verification passed."
