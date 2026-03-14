---
name: close-tabs
description: Close matching tabs in a chosen macOS browser by tab title or URL using AppleScript. Use when the user asks to close one or more tabs in Microsoft Edge, Google Chrome, Brave, Chromium, Safari, or another scriptable macOS browser, and the request includes the browser plus keywords or patterns that identify which tabs to close.
---

# Close Tabs

Use this skill to close only the tabs that match the requested browser and match text, while leaving unrelated tabs open.

## Inputs
- Required: `browser`
- Required: one or more tab match patterns
- Optional: `field` (`title`, `url`, or `either`; default `either`)
- Optional: `mode` (`contains`, `exact`, or `regex`; default `contains`)
- Optional: `dry_run` (`true` to preview matches before closing)

## Run
Use the bundled script:

```bash
python3 scripts/close_tabs.py --browser edge --pattern grubhub --pattern microsoft
python3 scripts/close_tabs.py --browser chrome --pattern docs.google.com --field url
python3 scripts/close_tabs.py --browser safari --pattern "Sign in" --mode exact --dry-run
python3 scripts/close_tabs.py --browser "Google Chrome" --pattern "calendar" --pattern "mail"
```

## Workflow
1. Resolve the browser alias to the macOS application name.
2. List every open tab across every open window in that browser.
3. Match patterns case-insensitively against the tab title, URL, or both.
4. Run with `--dry-run` first when the request is broad or ambiguous.
5. Close matches from the highest tab index downward so other tab indexes do not shift mid-run.

## Notes
- This skill is for macOS and depends on AppleScript-accessible browsers.
- Supported aliases are `edge`, `chrome`, `brave`, `chromium`, and `safari`.
- Any other `--browser` value is treated as the exact macOS application name.
- `--pattern` and `--tab` are interchangeable flags.
- Matching uses OR semantics: a tab closes if it matches any supplied pattern.
