#!/usr/bin/env python3
"""Download Salesforce case attachments/files by case number."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_VERSION = "65.0"


class SfCommandError(RuntimeError):
    """Raised when an sf CLI command fails."""


@dataclass
class DownloadItem:
    kind: str
    source_id: str
    name: str
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download artifacts linked to a Salesforce case number, including "
            "legacy Attachment records and Salesforce Files."
        )
    )
    parser.add_argument(
        "--case-number",
        required=True,
        help="CaseNumber to download artifacts for (for example 02622597).",
    )
    parser.add_argument(
        "--target-org",
        help="Salesforce org alias/username. Omit to use default authenticated org.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Output directory. Default: ./downloads/case-<case-number> "
            "relative to current working directory."
        ),
    )
    parser.add_argument(
        "--api-version",
        default=DEFAULT_API_VERSION,
        help=(
            "REST API version used for binary download endpoints "
            f"(default: {DEFAULT_API_VERSION})."
        ),
    )
    parser.add_argument(
        "--skip-legacy-attachments",
        action="store_true",
        help="Do not download classic Attachment records.",
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="Do not download Salesforce Files from ContentDocumentLink.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing local files instead of auto-renaming.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be downloaded without writing files.",
    )
    args = parser.parse_args()

    if not args.case_number.strip():
        parser.error("--case-number must be non-empty")
    if args.skip_legacy_attachments and args.skip_files:
        parser.error("Do not set both --skip-legacy-attachments and --skip-files")
    if not re.fullmatch(r"\d+(?:-\d+)?", args.case_number.strip()):
        # CaseNumber formats vary by org; this is a gentle warning, not a hard fail.
        print(
            "[WARN] --case-number format is unusual; proceeding anyway.",
            file=sys.stderr,
        )

    args.case_number = args.case_number.strip()
    return args


def escape_soql(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def run_sf_json(subcommand: list[str], target_org: str | None = None) -> dict[str, Any]:
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

    status = payload.get("status")
    if status not in (0, None):
        message = payload.get("message") or "Salesforce command returned a non-zero status"
        raise SfCommandError(str(message))
    return payload


def run_soql(soql: str, target_org: str | None = None) -> list[dict[str, Any]]:
    payload = run_sf_json(["data", "query", "--query", soql, "--json"], target_org)
    result = payload.get("result", {})
    records = result.get("records", [])
    if not isinstance(records, list):
        raise SfCommandError("Unexpected sf query JSON shape: result.records is not a list")
    return records


def sanitize_filename(raw: str, fallback: str) -> str:
    value = (raw or "").strip()
    if not value:
        value = fallback
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    return value[:180]


def ensure_extension(filename: str, extension: str | None) -> str:
    if not extension:
        return filename
    ext = extension.strip().lstrip(".")
    if not ext:
        return filename
    if filename.lower().endswith(f".{ext.lower()}"):
        return filename
    return f"{filename}.{ext}"


def unique_path(path: Path, overwrite: bool) -> Path:
    if overwrite or not path.exists():
        return path

    stem, suffix = os.path.splitext(path.name)
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def download_binary(
    endpoint: str,
    destination: Path,
    target_org: str | None,
) -> None:
    cmd = [
        "sf",
        "api",
        "request",
        "rest",
        endpoint,
        "--stream-to-file",
        str(destination),
    ]
    if target_org:
        cmd.extend(["--target-org", target_org])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise SfCommandError("sf CLI not found on PATH") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Download request failed"
        raise SfCommandError(message)


def load_case(case_number: str, target_org: str | None) -> dict[str, Any]:
    soql = (
        "SELECT Id, CaseNumber, Subject, Owner.Name, Status "
        "FROM Case "
        f"WHERE CaseNumber = '{escape_soql(case_number)}' "
        "ORDER BY CreatedDate DESC LIMIT 2"
    )
    records = run_soql(soql, target_org)
    if not records:
        raise SfCommandError(f"Case not found for CaseNumber '{case_number}'")
    if len(records) > 1:
        print(
            f"[WARN] Multiple records matched CaseNumber '{case_number}'. "
            "Using the newest row.",
            file=sys.stderr,
        )
    return records[0]


def query_legacy_attachments(case_id: str, target_org: str | None) -> list[dict[str, Any]]:
    soql = (
        "SELECT Id, Name, BodyLength, ContentType, CreatedDate "
        "FROM Attachment "
        f"WHERE ParentId = '{escape_soql(case_id)}' "
        "ORDER BY CreatedDate ASC"
    )
    return run_soql(soql, target_org)


def query_salesforce_files(case_id: str, target_org: str | None) -> list[dict[str, Any]]:
    soql = (
        "SELECT Id, ContentDocumentId, ContentDocument.Title, ContentDocument.FileExtension, "
        "ContentDocument.ContentSize, ContentDocument.LatestPublishedVersionId, "
        "ContentDocument.CreatedDate "
        "FROM ContentDocumentLink "
        f"WHERE LinkedEntityId = '{escape_soql(case_id)}' "
        "ORDER BY ContentDocument.CreatedDate ASC"
    )
    return run_soql(soql, target_org)


def main() -> int:
    args = parse_args()

    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else (Path.cwd() / "downloads" / f"case-{args.case_number}").resolve()
    )

    try:
        case = load_case(args.case_number, args.target_org)
        case_id = case["Id"]
    except (KeyError, SfCommandError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    try:
        attachments = [] if args.skip_legacy_attachments else query_legacy_attachments(case_id, args.target_org)
        files = [] if args.skip_files else query_salesforce_files(case_id, args.target_org)
    except SfCommandError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"Case: {case.get('CaseNumber')} ({case_id})")
    print(f"Subject: {case.get('Subject') or '-'}")
    print(f"Owner: {(case.get('Owner') or {}).get('Name', '-')}")
    print(f"Status: {case.get('Status') or '-'}")
    print(f"Legacy attachments: {len(attachments)}")
    print(f"Salesforce files: {len(files)}")
    print(f"Output directory: {output_dir}")

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadItem] = []

    for record in attachments:
        attachment_id = record.get("Id", "")
        raw_name = record.get("Name") or ""
        file_name = sanitize_filename(raw_name, f"attachment-{attachment_id}")
        destination = unique_path(output_dir / file_name, args.overwrite)
        if args.dry_run:
            print(f"[DRY-RUN] Attachment {attachment_id} -> {destination}")
            continue

        endpoint = f"/services/data/v{args.api_version}/sobjects/Attachment/{attachment_id}/Body"
        try:
            download_binary(endpoint, destination, args.target_org)
        except SfCommandError as exc:
            print(f"[ERROR] Failed to download attachment {attachment_id}: {exc}", file=sys.stderr)
            return 1
        downloaded.append(
            DownloadItem(kind="Attachment", source_id=attachment_id, name=file_name, path=destination)
        )

    for record in files:
        content_document = record.get("ContentDocument") or {}
        link_id = record.get("Id", "")
        version_id = content_document.get("LatestPublishedVersionId", "")
        title = content_document.get("Title") or ""
        extension = content_document.get("FileExtension")
        fallback = f"content-document-{record.get('ContentDocumentId') or link_id}"
        file_name = ensure_extension(sanitize_filename(title, fallback), extension)
        destination = unique_path(output_dir / file_name, args.overwrite)

        if not version_id:
            print(
                f"[WARN] Missing LatestPublishedVersionId for ContentDocumentLink {link_id}; skipped.",
                file=sys.stderr,
            )
            continue

        if args.dry_run:
            print(f"[DRY-RUN] File {link_id} (version {version_id}) -> {destination}")
            continue

        endpoint = f"/services/data/v{args.api_version}/sobjects/ContentVersion/{version_id}/VersionData"
        try:
            download_binary(endpoint, destination, args.target_org)
        except SfCommandError as exc:
            print(f"[ERROR] Failed to download file link {link_id}: {exc}", file=sys.stderr)
            return 1
        downloaded.append(
            DownloadItem(kind="File", source_id=link_id, name=file_name, path=destination)
        )

    if args.dry_run:
        print("Dry run complete.")
        return 0

    print("")
    if not downloaded:
        print("No artifacts downloaded (case has no matching attachments/files).")
        return 0

    print(f"Downloaded {len(downloaded)} artifact(s):")
    for item in downloaded:
        print(f"- {item.kind}: {item.name} ({item.source_id}) -> {item.path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
