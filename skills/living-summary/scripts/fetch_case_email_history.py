#!/usr/bin/env python3
"""Fetch Salesforce case email history by CaseNumber and export transcript files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any


class SfCommandError(RuntimeError):
    """Raised when sf CLI returns a failure or malformed payload."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull EmailMessage history for a Salesforce case number."
    )
    parser.add_argument(
        "--case-number",
        required=True,
        help="CaseNumber value (for example 02622597).",
    )
    parser.add_argument(
        "--target-org",
        help="Salesforce org alias/username. Omit to use default authenticated org.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Default: ./downloads/case-<case-number>/",
    )
    args = parser.parse_args()

    case_number = args.case_number.strip()
    if not case_number:
        parser.error("--case-number must be non-empty")
    args.case_number = case_number
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


def strip_record_attributes(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "attributes"}


def html_to_text(value: str) -> str:
    text = value
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</\s*div\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def resolve_body(email: dict[str, Any]) -> str:
    text_body = email.get("TextBody")
    if isinstance(text_body, str) and text_body.strip():
        return normalize_text(text_body)

    html_body = email.get("HtmlBody")
    if isinstance(html_body, str) and html_body.strip():
        return html_to_text(html_body)

    return "[No body content]"


def load_case(case_number: str, target_org: str | None) -> dict[str, Any]:
    soql = (
        "SELECT Id, CaseNumber, Subject, Status, Priority, CreatedDate "
        "FROM Case "
        f"WHERE CaseNumber = '{escape_soql(case_number)}' "
        "ORDER BY CreatedDate DESC LIMIT 2"
    )
    rows = run_soql(soql, target_org)
    if not rows:
        raise SfCommandError(f"Case not found for CaseNumber '{case_number}'")
    return strip_record_attributes(rows[0])


def load_email_history(case_id: str, target_org: str | None) -> list[dict[str, Any]]:
    soql = (
        "SELECT Id, ParentId, Incoming, MessageDate, CreatedDate, Status, Subject, "
        "FromAddress, ToAddress, CcAddress, BccAddress, TextBody, HtmlBody, "
        "MessageIdentifier, ThreadIdentifier, ReplyToEmailMessageId "
        "FROM EmailMessage "
        f"WHERE ParentId = '{escape_soql(case_id)}' "
        "ORDER BY MessageDate ASC, CreatedDate ASC"
    )
    rows = run_soql(soql, target_org)
    return [strip_record_attributes(r) for r in rows]


def format_transcript(case: dict[str, Any], emails: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("Case Metadata")
    lines.append(f"CaseNumber: {case.get('CaseNumber', '')}")
    lines.append(f"CaseId: {case.get('Id', '')}")
    lines.append(f"Subject: {case.get('Subject', '')}")
    lines.append(f"Status: {case.get('Status', '')}")
    lines.append(f"Priority: {case.get('Priority', '')}")
    lines.append(f"CreatedDate: {case.get('CreatedDate', '')}")
    lines.append(f"EmailCount: {len(emails)}")
    lines.append("")

    for idx, email in enumerate(emails, start=1):
        direction = "Inbound" if email.get("Incoming") else "Outbound"
        lines.append(f"===== Email {idx} =====")
        lines.append(f"Direction: {direction}")
        lines.append(f"MessageDate: {email.get('MessageDate', '')}")
        lines.append(f"CreatedDate: {email.get('CreatedDate', '')}")
        lines.append(f"Status: {email.get('Status', '')}")
        lines.append(f"Subject: {email.get('Subject', '')}")
        lines.append(f"FromAddress: {email.get('FromAddress', '')}")
        lines.append(f"ToAddress: {email.get('ToAddress', '')}")
        lines.append(f"CcAddress: {email.get('CcAddress', '')}")
        lines.append(f"BccAddress: {email.get('BccAddress', '')}")
        lines.append(f"MessageIdentifier: {email.get('MessageIdentifier', '')}")
        lines.append(f"ThreadIdentifier: {email.get('ThreadIdentifier', '')}")
        lines.append(f"ReplyToEmailMessageId: {email.get('ReplyToEmailMessageId', '')}")
        lines.append("Body:")
        lines.append(resolve_body(email))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (Path.cwd() / "downloads" / f"case-{args.case_number}").resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        case = load_case(args.case_number, args.target_org)
        emails = load_email_history(case["Id"], args.target_org)
    except (SfCommandError, KeyError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    transcript = format_transcript(case, emails)

    json_path = output_dir / "email_history.json"
    txt_path = output_dir / "email_history.txt"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case": case,
        "email_count": len(emails),
        "emails": emails,
        "transcript_file": str(txt_path),
    }

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    txt_path.write_text(transcript, encoding="utf-8")

    print(f"[OK] Case {case.get('CaseNumber')} email history exported.")
    print(f"[OK] JSON: {json_path}")
    print(f"[OK] Transcript: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
