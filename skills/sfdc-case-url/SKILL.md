---
name: sfdc-case-url
description: Resolve a Salesforce CaseNumber to its Lightning case URL using sf CLI. Use when asked to find, generate, or map a case URL from a case number (for example, 02813720 to a /lightning/r/Case/.../view URL) in production or sandbox orgs.
---

# SFDC Case URL

## Inputs
- Required: `case_number` (for example `02813720`)
- Optional: `target_org` (`sf` org alias/username)
- Optional: `lightning_base_url` override (for example `https://uipath.lightning.force.com`)

## Run
Use the bundled script:

```bash
bash scripts/get_case_url.sh \
  "<case_number>" \
  [target_org] \
  [lightning_base_url]
```

## Workflow
1. Query case by case number using `sf data query`.
2. Read the case `Id`.
3. Resolve org `instanceUrl` from `sf org display user` unless `lightning_base_url` is provided.
4. Convert host to Lightning domain when needed:
- `*.my.salesforce.com` -> `*.lightning.force.com`
5. Output final URL:
- `<lightning_base_url>/lightning/r/Case/<CaseId>/view`

## Command Pattern
Direct `sf` query pattern used by this skill:

```bash
sf data query --query "SELECT Id, CaseNumber FROM Case WHERE CaseNumber='<CaseNumber>' LIMIT 1" --json
```

## Example
Input:
- `case_number`: `02813720`

Output format:
- `https://uipath.lightning.force.com/lightning/r/Case/500Pa000018CCJpIAO/view`

## Notes
- Prefer script output as the source of truth instead of hand-constructing URLs.
- If case is not found, return a clear error.
