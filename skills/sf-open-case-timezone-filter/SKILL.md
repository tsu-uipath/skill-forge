---
name: sf-open-case-timezone-filter
description: Pull Salesforce cases owned by the current user with sf CLI, restrict to open/non-resolved cases, and list only cases where timezone is non-US or support availability preference is 24/7. Use when asked to triage "my open cases" by timezone/support-coverage criteria or produce a case list needing off-hours/regional handling.
---

# SF Open Case Timezone Filter

Use this skill to produce a focused case list for follow-the-sun and coverage checks.

## Inputs
- Optional: `target_org` (`sf` org alias/username)
- Optional: `timezone_field` (Case API field name for timezone)
- Optional: `support_field` (Case API field name for support availability preference)
- Optional: `limit` (records scanned before filter, default `200`)

## Run
Use the bundled script:

```bash
bash scripts/list_open_cases_by_tz_support.sh \
  [--target-org my-org-alias] \
  [--timezone-field Time_Zone__c] \
  [--support-field Support_Availability_Preference__c] \
  [--limit 200]
```

For machine-readable output:

```bash
bash scripts/list_open_cases_by_tz_support.sh --json
```

## Workflow
1. Resolve current Salesforce user (`OwnerId`) with `sf org display user --json`.
2. Query cases where:
- `IsClosed = false`
- `Status != 'Resolved'`
- `OwnerId = <current user>`
3. Detect timezone/support fields automatically from Case describe metadata unless explicit field names are passed.
4. Filter records to keep only cases where:
- timezone is non-US, or
- support availability preference indicates `24/7`.
5. Return a table (default) or JSON payload (`--json`).

## Notes
- Auto-detection is heuristic; pass `--timezone-field` and `--support-field` when your org has multiple similarly named fields.
- US timezone detection supports common Olson IDs (`America/...`), `US/...` aliases, and standard abbreviations (`EST`, `PST`, etc.).
