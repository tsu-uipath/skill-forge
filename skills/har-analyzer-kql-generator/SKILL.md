---
name: har-analyzer-kql-generator
description: Analyze HAR files to identify failed or slow requests, determine whether the response appears to be a UiPath Cloud error, and generate compact AppInsights KQL for targeted `requests` lookup plus full end-to-end trace correlation. Use when given a `.har` file or HAR JSON and asked to investigate browser/API failures, build KQL for Application Insights, or map HAR timestamps, URL paths, and trace IDs into AppInsights queries.
---

# HAR Analyzer + KQL Generator

## Overview

Use this skill to inspect HAR traffic, pick the most relevant failing request, and convert the evidence into AppInsights KQL that is ready to run with minimal cleanup.

Read [references/kql_patterns.md](references/kql_patterns.md) before composing the queries.

## Workflow

1. Identify the target request.
- Prefer genuine failures:
  - `response.status >= 400`
  - transport failures, aborted requests, empty response with error text, or other HAR error signals
- If there are multiple failures, focus on the most actionable one and mention any other notable failures briefly.
- If there are no failed requests, choose the longest-running request by HAR `time`.

2. Inspect whether this looks like a UiPath Cloud error.
- Check the response headers and body for UiPath-specific error signals.
- Examples: UiPath Cloud hostnames, UiPath service routes, UiPath-branded error payloads, correlation/trace headers, or service-specific JSON error envelopes.
- If the evidence does not clearly indicate a UiPath Cloud error, say that explicitly.

3. Extract correlation inputs for KQL.
- Capture the HAR request timestamp from `startedDateTime`.
- Capture the request URL path, without querystring noise unless it is essential to identification.
- Capture trace IDs or correlation IDs from headers or body when present.
- Treat HAR trace/correlation IDs as candidates for AppInsights `operation_Id`.
- If no trace ID is present, say so and build the first query from timestamp plus URL path only.

4. Produce the analysis summary first.
- Include method, host/path, status code, duration, timestamp, and why the request was selected.
- State whether it appears to be a UiPath Cloud error or not.
- Call out the exact evidence used for that conclusion.

5. Generate KQL query 1 for `requests`.
- Keep the query compact with no blank lines.
- Do not use `project` or `order by`.
- Include timestamp filtering.
- Include URL path logic.
- Include trace ID filtering when available.
- Keep `operation_Id` visible as the AppInsights trace ID field.

6. Generate KQL query 2 for the full end-to-end trace.
- Use a `union` across `requests`, `dependencies`, `traces`, `exceptions`, and `customEvents`.
- Filter by timestamp and trace ID.
- Keep the query compact with no blank lines.
- Do not use `project` or `order by`.

## Output Shape

Return:
- A short findings section
- `KQL 1` in a fenced `kusto` block
- `KQL 2` in a fenced `kusto` block

If the HAR does not contain enough data for a high-confidence trace match, say that and still provide the best timestamp/path-based query.
