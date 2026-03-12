---
name: sf-case-attachment-downloader
description: Download Salesforce case attachments by CaseNumber using sf CLI. Use when asked to fetch, save, or verify case attachments/files for a specific SFDC case, including both legacy Attachment records and Salesforce Files linked through ContentDocumentLink.
---

# SF Case Attachment Downloader

## Overview
Resolve a case from the provided `CaseNumber` and download all linked artifacts to local disk.
Handle both legacy `Attachment` binaries and Salesforce Files (`ContentDocumentLink` + `ContentVersion`).

## Prerequisites
- Authenticate Salesforce CLI (`sf`) to the target org.
- Ensure read access to `Case`, `Attachment`, `ContentDocumentLink`, and `ContentVersion`.

## Run
Use the script in `scripts/` with the case number.

```bash
python3 scripts/download_case_attachments.py \
  --case-number 02622597 \
  --target-org tim.su@uipath.com
```

## Common Options
- Set output directory: `--output-dir /absolute/path`
- Overwrite existing files: `--overwrite`
- Preview only (no download): `--dry-run`
- Skip legacy attachments: `--skip-legacy-attachments`
- Skip Salesforce Files: `--skip-files`
- Override API version for binary download endpoints: `--api-version 65.0`

## Output
- Default folder when `--output-dir` is omitted:
- `./downloads/case-<case-number>`
- Print case metadata, artifact counts, and saved file paths.
- Keep filenames safe for local filesystems and avoid collisions by appending numeric suffixes.
