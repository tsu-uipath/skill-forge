#!/usr/bin/env python3

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

SF_CLI_URL = "https://developer.salesforce.com/tools/salesforcecli"
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"


def truncate(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def run_command(argv: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "argv": argv,
        }
    except OSError as exc:
        return {
            "ok": False,
            "returncode": 126,
            "stdout": "",
            "stderr": str(exc),
            "argv": argv,
        }

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "argv": argv,
    }


def normalize_system(system: str) -> str:
    mapping = {
        "Darwin": "macOS",
        "Windows": "Windows",
        "Linux": "Linux",
    }
    return mapping.get(system, system)


def normalize_arch(machine: str) -> str:
    machine_lower = machine.lower()
    if machine_lower in {"x86_64", "amd64"}:
        return "x64"
    if machine_lower in {"arm64", "aarch64"}:
        return "arm64"
    return machine


def detect_download_label(os_name: str, arch: str) -> str:
    if os_name == "macOS":
        if arch == "arm64":
            return "macOS Apple Silicon"
        return "macOS Intel"
    if os_name == "Windows":
        return "Windows installer"
    return "Unsupported"


def codex_home_path() -> Path:
    env_value = os.environ.get("CODEX_HOME")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".codex"


def parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def collect_auth_records(node: Any, records: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        identity_keys = {"alias", "username", "orgId", "instanceUrl", "loginUrl"}
        if identity_keys.intersection(node.keys()):
            records.append(node)
        for value in node.values():
            collect_auth_records(value, records)
    elif isinstance(node, list):
        for item in node:
            collect_auth_records(item, records)


def inspect_sf(sf_path: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "installed": bool(sf_path),
        "path": sf_path,
        "healthy": False,
        "version_command": ["sf", "version", "--json", "--verbose"],
        "version": None,
        "version_detail": None,
        "error": None,
        "stderr": None,
        "stdout": None,
        "auth_checked": False,
        "auth_count": 0,
        "auth_entries": [],
        "auth_error": None,
    }
    if not sf_path:
        return result

    version_run = run_command(["sf", "version", "--json", "--verbose"])
    if version_run["ok"]:
        parsed = parse_json(version_run["stdout"])
        result["healthy"] = True
        if isinstance(parsed, dict):
            parsed_result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
            result["version"] = (
                parsed.get("cliVersion")
                or parsed.get("version")
                or parsed_result.get("cliVersion")
                or parsed_result.get("version")
            )
            result["version_detail"] = parsed
        else:
            result["stdout"] = truncate(version_run["stdout"])
    else:
        result["error"] = "sf version failed"
        result["stderr"] = truncate(version_run["stderr"])
        result["stdout"] = truncate(version_run["stdout"])
        return result

    auth_run = run_command(["sf", "org", "list", "auth", "--json"])
    result["auth_checked"] = True
    if auth_run["ok"]:
        parsed = parse_json(auth_run["stdout"])
        auth_entries: list[dict[str, Any]] = []
        collect_auth_records(parsed, auth_entries)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any, Any]] = set()
        for entry in auth_entries:
            key = (entry.get("username"), entry.get("alias"), entry.get("orgId"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "alias": entry.get("alias"),
                    "username": entry.get("username"),
                    "orgId": entry.get("orgId"),
                    "instanceUrl": entry.get("instanceUrl"),
                    "loginUrl": entry.get("loginUrl"),
                    "isDefaultUsername": entry.get("isDefaultUsername"),
                    "isDefaultDevHubUsername": entry.get("isDefaultDevHubUsername"),
                }
            )
        result["auth_entries"] = deduped
        result["auth_count"] = len(deduped)
    else:
        result["auth_error"] = truncate(auth_run["stderr"] or auth_run["stdout"])

    return result


def parse_mcp_get_output(stdout: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in stdout.splitlines() if line.strip()]
    parsed: dict[str, Any] = {}
    if not lines:
        return parsed
    parsed["name"] = lines[0].strip()
    for line in lines[1:]:
        stripped = line.strip()
        if ": " not in stripped:
            continue
        key, value = stripped.split(": ", 1)
        parsed[key] = value
    return parsed


def inspect_atlassian_mcp(codex_path: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "expected_name": "atlassian",
        "expected_url": ATLASSIAN_MCP_URL,
        "codex_present": bool(codex_path),
        "mcp_commands_available": False,
        "configured": False,
        "enabled": None,
        "matches_expected": False,
        "status": "codex_missing" if not codex_path else "unknown",
        "details": {},
        "error": None,
    }
    if not codex_path:
        return result

    help_run = run_command(["codex", "mcp", "--help"])
    if not help_run["ok"]:
        result["status"] = "mcp_cli_unavailable"
        result["error"] = truncate(help_run["stderr"] or help_run["stdout"])
        return result

    result["mcp_commands_available"] = True
    get_run = run_command(["codex", "mcp", "get", "atlassian"])
    if get_run["ok"]:
        details = parse_mcp_get_output(get_run["stdout"])
        enabled_value = details.get("enabled")
        enabled = None
        if enabled_value is not None:
            enabled = enabled_value.lower() == "true"
        matches = details.get("url") == ATLASSIAN_MCP_URL and enabled is True
        result["configured"] = True
        result["enabled"] = enabled
        result["matches_expected"] = matches
        result["status"] = "configured_match" if matches else "configured_mismatch"
        result["details"] = details
        return result

    combined_error = truncate(get_run["stderr"] or get_run["stdout"])
    if "No MCP server named 'atlassian' found." in (get_run["stderr"] or ""):
        result["status"] = "missing"
        result["error"] = combined_error
        return result

    result["status"] = "error"
    result["error"] = combined_error
    return result


def build_recommended_steps(state: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    platform_state = state["platform"]
    salesforce = state["salesforce"]
    atlassian = state["atlassian_mcp"]

    if not platform_state["supported"]:
        steps.append("Stop. This helper only supports macOS and Windows.")
        return steps

    if not salesforce["installed"]:
        steps.append(
            f"Install Salesforce CLI from {SF_CLI_URL} and choose {platform_state['sf_download_label']}."
        )
    elif not salesforce["healthy"]:
        error = salesforce.get("stderr") or salesforce.get("error") or "Unknown sf error."
        steps.append(f"Repair the existing sf CLI before continuing. Current error: {error}")
    else:
        if salesforce["auth_count"] == 0:
            steps.append(
                "Salesforce CLI is healthy but no local org auth was found. Run sf org login web only if the user wants org access."
            )
        else:
            steps.append(
                f"Salesforce CLI is healthy and {salesforce['auth_count']} local org authorization record(s) were found."
            )

    if atlassian["status"] == "codex_missing":
        steps.append("Codex CLI is not on PATH. Use the manual config fallback path if Atlassian MCP must be added.")
    elif atlassian["status"] == "mcp_cli_unavailable":
        steps.append("Codex CLI is present but MCP commands are unavailable. Use the manual config fallback.")
    elif atlassian["status"] == "missing":
        steps.append(f"Add Atlassian MCP with: codex mcp add atlassian --url {ATLASSIAN_MCP_URL}")
    elif atlassian["status"] == "configured_match":
        steps.append("Atlassian MCP already matches the expected remote server. Re-run codex mcp login atlassian only if re-authentication is needed.")
    elif atlassian["status"] == "configured_mismatch":
        steps.append("An atlassian MCP entry already exists but does not match the expected config. Ask before replacing it.")
    elif atlassian["status"] == "error":
        steps.append(f"Investigate the Codex MCP error before changing config: {atlassian['error']}")

    return steps


def build_state(opened_browser: bool | None) -> dict[str, Any]:
    system = platform.system()
    os_name = normalize_system(system)
    arch = normalize_arch(platform.machine())
    sf_path = shutil.which("sf")
    codex_path = shutil.which("codex")
    codex_home = codex_home_path()

    state: dict[str, Any] = {
        "platform": {
            "system": system,
            "os_name": os_name,
            "supported": os_name in {"macOS", "Windows"},
            "architecture": arch,
            "sf_download_label": detect_download_label(os_name, arch),
        },
        "paths": {
            "sf": sf_path,
            "codex": codex_path,
            "codex_home": str(codex_home),
            "config_toml": str(codex_home / "config.toml"),
        },
        "salesforce": inspect_sf(sf_path),
        "atlassian_mcp": inspect_atlassian_mcp(codex_path),
        "manual_fallback": {
            "config_path": str(codex_home / "config.toml"),
            "config_block": '[mcp_servers.atlassian]\nurl = "https://mcp.atlassian.com/v1/mcp"\nenabled = true',
        },
        "links": {
            "salesforce_cli": SF_CLI_URL,
            "atlassian_mcp": ATLASSIAN_MCP_URL,
        },
        "browser_open_attempted": opened_browser is not None,
        "browser_opened": opened_browser,
    }
    state["recommended_next_steps"] = build_recommended_steps(state)
    return state


def print_human_summary(state: dict[str, Any]) -> None:
    platform_state = state["platform"]
    salesforce = state["salesforce"]
    atlassian = state["atlassian_mcp"]
    paths = state["paths"]

    print(f"Platform: {platform_state['os_name']} {platform_state['architecture']}")
    print(f"Supported: {'yes' if platform_state['supported'] else 'no'}")
    print(f"Salesforce CLI path: {paths['sf'] or 'not found'}")
    if not salesforce["installed"]:
        print(f"Salesforce download target: {platform_state['sf_download_label']}")
    elif salesforce["healthy"]:
        print(f"Salesforce CLI health: ok ({salesforce.get('version') or 'version available'})")
        print(f"Salesforce auth records: {salesforce['auth_count']}")
    else:
        print("Salesforce CLI health: failed")
        if salesforce.get("stderr"):
            print(f"sf error: {salesforce['stderr']}")

    print(f"Codex path: {paths['codex'] or 'not found'}")
    print(f"Atlassian MCP status: {atlassian['status']}")
    if atlassian["configured"]:
        print(f"Atlassian MCP URL: {atlassian['details'].get('url')}")
        print(f"Atlassian MCP enabled: {atlassian['details'].get('enabled')}")
    elif atlassian.get("error"):
        print(f"Atlassian MCP detail: {atlassian['error']}")

    print(f"Manual config path: {state['manual_fallback']['config_path']}")
    print("Recommended next steps:")
    for step in state["recommended_next_steps"]:
        print(f"- {step}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Codex, Salesforce CLI, and Atlassian MCP setup for macOS or Windows."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--open-sf-page",
        action="store_true",
        help="Open the official Salesforce CLI download page in the default browser.",
    )
    args = parser.parse_args()

    opened_browser: bool | None = None
    if args.open_sf_page:
        opened_browser = webbrowser.open(SF_CLI_URL)

    state = build_state(opened_browser)
    if args.json:
        json.dump(state, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_human_summary(state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
