#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  get_case_url.sh "<case_number>" [target_org] [lightning_base_url]

Arguments:
  case_number         Salesforce CaseNumber (for example: 02813720)
  target_org          Optional sf org alias/username. Uses default org if omitted.
  lightning_base_url  Optional override (for example: https://uipath.lightning.force.com)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

CASE_NUMBER="$1"
TARGET_ORG="${2:-}"
LIGHTNING_BASE_URL="${3:-}"

# Keep input strict to avoid SOQL injection when interpolating CaseNumber.
if [[ ! "$CASE_NUMBER" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "Invalid case_number: use only letters and digits." >&2
  exit 1
fi

run_sf_json() {
  "$@" --json 2>/dev/null
}

extract_case_id() {
  python3 - <<'PY' "$1"
import json
import sys

raw = sys.argv[1]
start = raw.find("{")
if start == -1:
    print("Unable to parse sf JSON output.", file=sys.stderr)
    sys.exit(1)
data = json.loads(raw[start:])
records = (data.get("result") or {}).get("records") or []
if not records:
    sys.exit(3)
case_id = records[0].get("Id")
if not case_id:
    print("Case record missing Id.", file=sys.stderr)
    sys.exit(1)
print(case_id)
PY
}

derive_lightning_base_url() {
  python3 - <<'PY' "$1"
import json
import sys
from urllib.parse import urlparse

raw = sys.argv[1]
start = raw.find("{")
if start == -1:
    print("Unable to parse sf JSON output.", file=sys.stderr)
    sys.exit(1)
data = json.loads(raw[start:])
instance_url = (data.get("result") or {}).get("instanceUrl")
if not instance_url:
    print("instanceUrl missing from sf org display user output.", file=sys.stderr)
    sys.exit(1)

host = urlparse(instance_url).netloc
if not host:
    print(f"Could not parse host from instanceUrl: {instance_url}", file=sys.stderr)
    sys.exit(1)

if host.endswith(".lightning.force.com"):
    base = f"https://{host}"
elif host.endswith(".my.salesforce.com"):
    base = "https://" + host.replace(".my.salesforce.com", ".lightning.force.com")
else:
    base = f"https://{host}"

print(base.rstrip("/"))
PY
}

QUERY="SELECT Id, CaseNumber FROM Case WHERE CaseNumber='${CASE_NUMBER}' LIMIT 1"
QUERY_CMD=(sf data query --query "$QUERY")
if [[ -n "$TARGET_ORG" ]]; then
  QUERY_CMD+=(--target-org "$TARGET_ORG")
fi

if ! QUERY_JSON="$(run_sf_json "${QUERY_CMD[@]}")"; then
  echo "Failed to query case ${CASE_NUMBER} via sf CLI." >&2
  exit 1
fi

if ! CASE_ID="$(extract_case_id "$QUERY_JSON")"; then
  rc=$?
  if [[ $rc -eq 3 ]]; then
    echo "Case not found: ${CASE_NUMBER}" >&2
  else
    echo "Failed to parse case query response for ${CASE_NUMBER}." >&2
  fi
  exit 1
fi

if [[ -z "$LIGHTNING_BASE_URL" ]]; then
  ORG_CMD=(sf org display user)
  if [[ -n "$TARGET_ORG" ]]; then
    ORG_CMD+=(--target-org "$TARGET_ORG")
  fi
  if ! ORG_JSON="$(run_sf_json "${ORG_CMD[@]}")"; then
    echo "Failed to resolve org instance URL via sf CLI." >&2
    exit 1
  fi
  LIGHTNING_BASE_URL="$(derive_lightning_base_url "$ORG_JSON")"
fi

LIGHTNING_BASE_URL="${LIGHTNING_BASE_URL%/}"
CASE_URL="${LIGHTNING_BASE_URL}/lightning/r/Case/${CASE_ID}/view"
echo "$CASE_URL"

