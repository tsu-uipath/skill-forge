#!/usr/bin/env python3
"""Update Salesforce case living-summary custom fields from a summary text file."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from html import escape
from pathlib import Path
from typing import Any

SECTION_TO_FIELD = {
    "problem": "Problem__c",
    "cause": "Cause__c",
    "validation_steps": "Validation__c",
    "solution_or_possible_solution": "Solution__c",
    "solution_instructions": "Solution_Instructions__c",
}

MISSING_VALUE = "Information not available."
REST_API_VERSION = "v66.0"


class SfCommandError(RuntimeError):
    """Raised when sf CLI returns an error or malformed output."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update Case living-summary custom fields from structured summary text."
    )
    parser.add_argument(
        "--case-number",
        required=True,
        help="CaseNumber to update (for example 02815643).",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        required=True,
        help="Path to the generated structured summary text file.",
    )
    parser.add_argument(
        "--target-org",
        help="Salesforce org alias/username. Omit to use default authenticated org.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print field mappings without updating Salesforce.",
    )
    args = parser.parse_args()

    case_number = args.case_number.strip()
    if not case_number:
        parser.error("--case-number must be non-empty")
    args.case_number = case_number

    if not args.summary_file.exists():
        parser.error(f"--summary-file not found: {args.summary_file}")
    if not args.summary_file.is_file():
        parser.error(f"--summary-file is not a file: {args.summary_file}")

    return args


def escape_soql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def run_sf_json(subcommand: list[str], target_org: str | None) -> dict[str, Any]:
    cmd = ["sf", *subcommand]
    if target_org:
        cmd.extend(["--target-org", target_org])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SfCommandError("sf CLI not found on PATH") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Unknown sf CLI error"
        raise SfCommandError(message)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SfCommandError("sf CLI returned non-JSON output") from exc

    if payload.get("status") not in (0, None):
        message = payload.get("message") or "Salesforce command returned non-zero status"
        raise SfCommandError(str(message))

    return payload


def run_soql(soql: str, target_org: str | None) -> list[dict[str, Any]]:
    payload = run_sf_json(["data", "query", "--query", soql, "--json"], target_org)
    records = payload.get("result", {}).get("records", [])
    if not isinstance(records, list):
        raise SfCommandError("Unexpected Salesforce response: result.records is not a list")
    return records


def normalize_heading_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^#+\s*", "", text)
    if text.startswith("**") and text.endswith("**") and len(text) > 4:
        text = text[2:-2].strip()
    return text


def detect_section(line: str) -> tuple[str, str] | None:
    text = normalize_heading_line(line)

    candidates = [
        ("problem", "Problem"),
        ("cause", "Cause"),
        ("validation_steps", "Validation Steps"),
        ("solution_or_possible_solution", "Solution / Possible Solution"),
        ("solution_or_possible_solution", "Possible Solution"),
        ("solution_or_possible_solution", "Solution"),
        ("solution_instructions", "Solution Instructions"),
    ]

    for key, label in candidates:
        if text.lower().startswith(label.lower()):
            remainder = text[len(label) :].strip()
            if not remainder:
                return key, ""
            if remainder.startswith(":"):
                return key, remainder[1:].strip()
    return None


def parse_summary_sections(summary_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_TO_FIELD}
    current_key: str | None = None

    for raw_line in summary_text.splitlines():
        section_match = detect_section(raw_line)
        if section_match:
            current_key, inline_content = section_match
            if inline_content:
                sections[current_key].append(inline_content)
            continue

        if current_key is not None:
            sections[current_key].append(raw_line)

    cleaned: dict[str, str] = {}
    for key, lines in sections.items():
        value = "\n".join(lines).strip()
        cleaned[key] = value if value else MISSING_VALUE
    return cleaned


def load_case_id(case_number: str, target_org: str | None) -> str:
    soql = (
        "SELECT Id, CaseNumber "
        "FROM Case "
        f"WHERE CaseNumber = '{escape_soql(case_number)}' "
        "ORDER BY CreatedDate DESC LIMIT 2"
    )
    rows = run_soql(soql, target_org)
    if not rows:
        raise SfCommandError(f"Case not found for CaseNumber '{case_number}'")
    return str(rows[0]["Id"])


def to_salesforce_rich_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines:
        lines = [MISSING_VALUE]

    paragraphs: list[str] = []
    for line in lines:
        if line == "":
            paragraphs.append("<p>&nbsp;</p>")
            continue
        paragraphs.append(f"<p>{escape(line, quote=False)}</p>")
    return "".join(paragraphs)


def build_update_payload(sections: dict[str, str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for section_key, field_name in SECTION_TO_FIELD.items():
        raw_value = sections.get(section_key, MISSING_VALUE).strip() or MISSING_VALUE
        rich_text = to_salesforce_rich_text(raw_value)
        payload[field_name] = rich_text
    return payload


def update_case_fields(case_id: str, update_payload: dict[str, str], target_org: str | None) -> None:
    cmd = [
        "sf",
        "api",
        "request",
        "rest",
        f"/services/data/{REST_API_VERSION}/sobjects/Case/{case_id}",
        "--method",
        "PATCH",
        "--header",
        "Content-Type: application/json",
        "--header",
        "Sforce-Auto-Assign:false",
        "--body",
        json.dumps(update_payload),
    ]
    if target_org:
        cmd.extend(["--target-org", target_org])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SfCommandError("sf CLI not found on PATH") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Case update failed"
        raise SfCommandError(message)


def main() -> int:
    args = parse_args()

    summary_text = args.summary_file.read_text(encoding="utf-8")
    sections = parse_summary_sections(summary_text)
    update_payload = build_update_payload(sections)

    try:
        case_id = load_case_id(args.case_number, args.target_org)
    except SfCommandError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[DRY-RUN] CaseNumber: {args.case_number}")
        print(f"[DRY-RUN] CaseId: {case_id}")
        for section_key, field_name in SECTION_TO_FIELD.items():
            print("")
            print(f"[DRY-RUN] {field_name} ({section_key})")
            print(sections.get(section_key, MISSING_VALUE))
        return 0

    try:
        update_case_fields(case_id, update_payload, args.target_org)
    except SfCommandError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Updated Case {args.case_number} ({case_id}) living summary fields.")
    print("[OK] Fields: Problem__c, Cause__c, Validation__c, Solution__c, Solution_Instructions__c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
