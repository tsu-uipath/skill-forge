# HAR to AppInsights Mapping

## Field mapping

- HAR `startedDateTime` -> AppInsights `timestamp`
- HAR request URL -> AppInsights `url`
- HAR URL path -> `tostring(parse_url(url).Path)`
- HAR trace/correlation id -> AppInsights `operation_Id` when the values match

## Query rules

- Keep output compact: no blank lines
- Do not use `project`
- Do not use `order by`
- Use `extend` when a parsed URL path column is helpful
- Use a bounded timestamp window around the HAR request time, usually a few minutes on either side

## Requests query template

```kusto
requests
| where timestamp between (datetime(<start>) .. datetime(<end>))
| extend UrlPath = tostring(parse_url(url).Path)
| where UrlPath == "<path>"
| where operation_Id == "<trace-id>"
```

If there is no trace ID, omit the `operation_Id` filter and rely on the timestamp window plus path.

If there are multiple candidate failures, use `in (...)` or explicit `or` conditions for paths and trace IDs.

## Full trace query template

```kusto
union withsource=TableName requests, dependencies, traces, exceptions, customEvents
| where timestamp between (datetime(<start>) .. datetime(<end>))
| where operation_Id == "<trace-id>"
```

If there are multiple trace IDs, use `operation_Id in (...)`.

If the HAR only gives a likely timestamp and no trace ID, say that the second query is lower confidence and widen the timestamp window conservatively.
