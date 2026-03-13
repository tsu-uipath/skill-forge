---
name: codex-sf-atlassian-setup
description: Bootstrap Codex on macOS or Windows for Salesforce CLI and Atlassian remote MCP. Use when asked to set up a new Codex machine, verify or install `sf`, configure the `atlassian` MCP server at `https://mcp.atlassian.com/v1/mcp`, or optionally log into a Salesforce org after setup.
---

# Codex SF + Atlassian Setup

Use this skill for cross-platform Codex onboarding on macOS and Windows.

## Scope

- Supported OS: macOS and Windows.
- Out of scope: Linux, Atlassian CLI (`acli`), and package-manager-first Salesforce installs.
- Start with inspection. Only mutate after you have current state from the helper script.

## Start Here

Run the helper script first and read its output before making any changes.

macOS:

```bash
cd "$HOME/.codex/skills/codex-sf-atlassian-setup"
python3 scripts/check_setup.py --json
```

Windows:

```powershell
Set-Location "$HOME\.codex\skills\codex-sf-atlassian-setup"
py -3 scripts\check_setup.py --json
```

The script reports:

- OS and architecture.
- Whether `sf` is on `PATH` and whether `sf version --json --verbose` succeeds.
- Whether local Salesforce org auth already exists via `sf org list auth --json`.
- Whether `codex` is on `PATH`.
- Whether `codex mcp get atlassian` matches the expected remote server.
- The manual fallback config path and the exact Atlassian config block.

## Workflow

1. If the script reports an unsupported OS, stop and say this skill only supports macOS and Windows.
2. If `sf` is missing:
   - Open the official Salesforce CLI page with the helper script:

   macOS:

   ```bash
   python3 scripts/check_setup.py --open-sf-page
   ```

   Windows:

   ```powershell
   py -3 scripts\check_setup.py --open-sf-page
   ```

   - Tell the user which download to choose based on the script output:
     - `macOS Apple Silicon`
     - `macOS Intel`
     - `Windows installer`
   - After the installer finishes, rerun the helper script and continue from the new state.
3. If `sf` is present but `sf version` fails, stop and surface the actual stderr. Treat this as a repair or permissions problem, not as proof that the CLI is absent.
4. If `sf` is healthy and the user wants Salesforce auth:
   - Check the helper output first. If local auth already exists, report it and only re-authenticate if the user asks.
   - Otherwise run `sf org login web` with only the flags the user actually needs:

   ```bash
   sf org login web
   sf org login web --alias <alias>
   sf org login web --instance-url <instance-url> --set-default
   sf org login web --alias <alias> --set-default-dev-hub
   sf org login web --browser chrome|edge|firefox
   ```

   - Use `--set-default` for a default scratch org, sandbox, or production org.
   - Use `--set-default-dev-hub` only for a Dev Hub.
   - If the user does not want Salesforce auth, stop after verifying the CLI.
5. For Atlassian MCP, prefer Codex CLI commands over direct config edits:
   - If `codex mcp get atlassian` reports the expected URL and enabled state, leave it alone.
   - If the `atlassian` entry is missing, run:

   ```bash
   codex mcp add atlassian --url https://mcp.atlassian.com/v1/mcp
   ```

   - If an `atlassian` entry exists but does not match the expected URL or state, stop and ask before replacing it.
6. After a successful add, or when the user asks to re-authenticate Atlassian, run:

   ```bash
   codex mcp login atlassian
   ```

7. Tell the user to complete the OAuth flow in the browser, then restart Codex and rerun this skill. Do not assume new MCP tools become available inside the current session.
8. After restart:
   - If Atlassian MCP tools are available in the session, verify with `atlassianUserInfo`.
   - Otherwise confirm `codex mcp get atlassian` still shows the expected server and explain that tool availability refreshes after restart.

## Manual Fallback

Only use this when `codex mcp` commands are unavailable or the user explicitly wants manual config edits.

1. Resolve the config path from the helper script output.
2. Add this block if it is missing:

   ```toml
   [mcp_servers.atlassian]
   url = "https://mcp.atlassian.com/v1/mcp"
   enabled = true
   ```

3. Restart Codex.
4. Run `codex mcp login atlassian` if the CLI supports it after restart, or otherwise guide the user through the OAuth prompt in the UI that follows.

## Guardrails

- Do not use `acli`; this skill is for Atlassian MCP setup in Codex, not Atlassian CLI setup.
- Do not overwrite a non-standard `atlassian` entry without asking first.
- Do not assume Homebrew, winget, or Chocolatey is available.
- Prefer the official Salesforce installer page over package-manager instructions.
- Keep the user informed when a browser interaction or Codex restart is required.

## Reference Map

- Read `references/current-setup-sources.md` when you need the authoritative URLs or the current `/v1/mcp` versus `/v1/sse` note.
