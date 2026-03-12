---
name: amer-platform-cases-overview
description: Pull Salesforce cases for the AMER platform manager with sf CLI, filter to open non-resolved cases, group them by case owner, and generate CSV plus SVG overview artifacts. Use when asked for an AMER platform case overview, refreshed owner graph, or current owner breakdown for manager id `0051Q00000D8aCi`.
---

# AMER Platform Cases Overview

Use this skill to regenerate the AMER platform case overview from live Salesforce data.

## Inputs

- Optional: `target_org` (`sf` org alias or username)
- Optional: `manager_id` (defaults to `0051Q00000D8aCi`)
- Optional: `outdir` (defaults to `output/spreadsheet` under the current workspace)

## Run

Run the bundled script from the target workspace so the output files land in that workspace:

```bash
python3 scripts/run_overview.py \
  [--target-org my-org-alias] \
  [--manager-id 0051Q00000D8aCi] \
  [--outdir output/spreadsheet]
```

## Workflow

1. Query Salesforce `Case` records where:
- `OwnerId IN (SELECT Id FROM User WHERE ManagerId = '<manager_id>')`
- `IsClosed = false`
- `Status != 'Resolved'`
2. Export the matching cases to a raw CSV file.
3. Aggregate the cases by owner and write a summary CSV.
4. Generate an SVG bar chart and a Markdown summary table.
5. Report the total cases, owner count, and top owners back to the user.

## Outputs

For manager `0051Q00000D8aCi`, the default filenames are:

- `manager_0051Q00000D8aCi_open_non_resolved_cases.csv`
- `manager_0051Q00000D8aCi_open_non_resolved_by_owner.csv`
- `manager_0051Q00000D8aCi_open_non_resolved_by_owner.svg`
- `manager_0051Q00000D8aCi_open_non_resolved_by_owner.md`

## Notes

- The script uses the default `sf` org unless `--target-org` is passed.
- Keep the filter as `IsClosed = false AND Status != 'Resolved'` unless the user explicitly asks for a different status definition.
- If the user wants a different manager, pass `--manager-id` and rerun the script.
