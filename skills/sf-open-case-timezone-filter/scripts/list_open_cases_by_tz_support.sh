#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  list_open_cases_by_tz_support.sh [--target-org ORG_ALIAS] [--timezone-field API_NAME] [--support-field API_NAME] [--limit N] [--json]

Description:
  Query Salesforce Cases owned by the current user where:
  - Case is open and status is not Resolved
  Then list only cases where:
  - timezone is not a US timezone
    OR
  - support availability preference indicates 24/7

Options:
  --target-org ORG_ALIAS   Optional sf org alias/username.
  --timezone-field NAME    Optional Case field API name for timezone.
  --support-field NAME     Optional Case field API name for support availability preference.
  --limit N                Optional max records to scan before filtering (default: 200).
  --json                   Output JSON instead of table text.
  -h, --help               Show this help.
EOF
}

TARGET_ORG=""
TIMEZONE_FIELD=""
SUPPORT_FIELD=""
LIMIT=200
OUTPUT_JSON=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-org)
      TARGET_ORG="${2:-}"
      shift 2
      ;;
    --timezone-field)
      TIMEZONE_FIELD="${2:-}"
      shift 2
      ;;
    --support-field)
      SUPPORT_FIELD="${2:-}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --json)
      OUTPUT_JSON=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v sf >/dev/null 2>&1; then
  echo "Missing dependency: sf CLI" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Missing dependency: jq" >&2
  exit 1
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [[ "$LIMIT" -lt 1 ]]; then
  echo "--limit must be a positive integer" >&2
  exit 1
fi

sf_cmd_with_org() {
  if [[ -n "$TARGET_ORG" ]]; then
    sf "$@" --target-org "$TARGET_ORG"
  else
    sf "$@"
  fi
}

sf_query_json() {
  local query="$1"
  if [[ -n "$TARGET_ORG" ]]; then
    sf data query --json --query "$query" --target-org "$TARGET_ORG"
  else
    sf data query --json --query "$query"
  fi
}

detect_field() {
  local describe_json="$1"
  local requested="$2"
  local mode="$3"

  if [[ -n "$requested" ]]; then
    echo "$requested"
    return 0
  fi

  if [[ "$mode" == "timezone" ]]; then
    jq -r '
      .result.fields
      | map(.name)
      | map(select(test("(?i)time.?zone")))
      | .[0] // ""
    ' <<<"$describe_json"
    return 0
  fi

  jq -r '
    .result.fields
    | map(.name)
    | map(select(test("(?i)support.*availability|availability.*support|support.*hours|24.?7")))
    | .[0] // ""
  ' <<<"$describe_json"
}

describe_json="$(sf_cmd_with_org sobject describe --sobject Case --json)"

timezone_field="$(detect_field "$describe_json" "$TIMEZONE_FIELD" "timezone")"
support_field="$(detect_field "$describe_json" "$SUPPORT_FIELD" "support")"

if [[ -z "$timezone_field" ]]; then
  echo "Could not detect timezone field on Case. Pass --timezone-field <API_NAME>." >&2
  exit 1
fi

if [[ -z "$support_field" ]]; then
  echo "Could not detect support availability field on Case. Pass --support-field <API_NAME>." >&2
  exit 1
fi

user_info="$(sf_cmd_with_org org display user --json)"
owner_id="$(jq -r '.result.id // .result.userId // empty' <<<"$user_info")"

if [[ -z "$owner_id" ]]; then
  echo "Could not determine current user ID from sf org display user." >&2
  exit 1
fi

soql="SELECT Id, CaseNumber, Subject, Status, ${timezone_field}, ${support_field}
FROM Case
WHERE IsClosed = false
  AND Status != 'Resolved'
  AND OwnerId = '${owner_id}'
ORDER BY LastModifiedDate DESC
LIMIT ${LIMIT}"

query_json="$(sf_query_json "$soql")"

filtered_json="$(
  jq --arg tz "$timezone_field" --arg sp "$support_field" '
    def norm($v): ($v // "" | tostring | gsub("^\\s+|\\s+$"; ""));
    def is_us_timezone($t):
      ($t | test("(?i)(America/(New_York|Detroit|Louisville|Indianapolis|Chicago|Menominee|North_Dakota/Center|North_Dakota/New_Salem|North_Dakota/Beulah|Denver|Boise|Phoenix|Los_Angeles|Anchorage|Adak|Honolulu|Juneau|Sitka|Metlakatla|Yakutat|Nome)|US/(Eastern|Central|Mountain|Pacific|Alaska|Hawaii)|\\b(EST|EDT|CST|CDT|MST|MDT|PST|PDT|AKST|AKDT|HST)\\b|Eastern( Standard| Daylight)? Time( \\(US ?& ?Canada\\))?|Central( Standard| Daylight)? Time( \\(US ?& ?Canada\\))?|Mountain( Standard| Daylight)? Time( \\(US ?& ?Canada\\))?|Pacific( Standard| Daylight)? Time( \\(US ?& ?Canada\\))?|\\bUS ?& ?Canada\\b)"));
    def is_247($v):
      ($v | test("(?i)24\\s*[/x-]?\\s*7|24\\s*hours|always|round\\s*the\\s*clock"));
    (.result.records // [])
    | map({
        Id,
        CaseNumber,
        Subject: (.Subject // ""),
        Status: (.Status // ""),
        Timezone: norm(.[$tz]),
        SupportAvailabilityPreference: norm(.[$sp])
      })
    | map(. + {
        IsNonUSTimezone: ((.Timezone != "") and (is_us_timezone(.Timezone) | not)),
        Is247SupportPreference: is_247(.SupportAvailabilityPreference)
      })
    | map(select(.IsNonUSTimezone or .Is247SupportPreference))
  ' <<<"$query_json"
)"

if [[ "$OUTPUT_JSON" -eq 1 ]]; then
  jq -n \
    --arg timezoneField "$timezone_field" \
    --arg supportField "$support_field" \
    --arg ownerId "$owner_id" \
    --argjson records "$filtered_json" '
      {
        timezoneField: $timezoneField,
        supportField: $supportField,
        ownerId: $ownerId,
        count: ($records | length),
        records: $records
      }
    '
  exit 0
fi

count="$(jq 'length' <<<"$filtered_json")"
echo "Timezone field: $timezone_field"
echo "Support availability field: $support_field"
echo "OwnerId: $owner_id"
echo "Matching cases: $count"

if [[ "$count" -eq 0 ]]; then
  exit 0
fi

tmp_tsv="$(mktemp -t sf_open_case_tz_support.XXXXXX.tsv)"
trap 'rm -f "$tmp_tsv"' EXIT

jq -r '
  (["CaseNumber", "Status", "Timezone", "SupportAvailabilityPreference", "Subject"] | @tsv),
  (.[] | [.CaseNumber, .Status, .Timezone, .SupportAvailabilityPreference, .Subject] | @tsv)
' <<<"$filtered_json" > "$tmp_tsv"

if command -v column >/dev/null 2>&1; then
  column -t -s $'\t' "$tmp_tsv"
else
  cat "$tmp_tsv"
fi
