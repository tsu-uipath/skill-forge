#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path


DEFAULT_MANAGER_ID = "0051Q00000D8aCi"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull AMER platform cases from Salesforce and generate an owner overview.",
    )
    parser.add_argument("--target-org", help="sf target org alias or username")
    parser.add_argument(
        "--manager-id",
        default=DEFAULT_MANAGER_ID,
        help=f"Salesforce User.ManagerId to query (default: {DEFAULT_MANAGER_ID})",
    )
    parser.add_argument(
        "--outdir",
        default="output/spreadsheet",
        help="Output directory for the generated files",
    )
    return parser.parse_args()


def build_soql(manager_id: str) -> str:
    return (
        "SELECT Id, CaseNumber, OwnerId, Owner.Name, Subject, Status, Priority, "
        "CreatedDate, LastModifiedDate, Account.Name "
        "FROM Case "
        "WHERE OwnerId IN (SELECT Id FROM User WHERE ManagerId = '{manager_id}') "
        "AND IsClosed = false "
        "AND Status != 'Resolved' "
        "ORDER BY Owner.Name, CreatedDate DESC"
    ).format(manager_id=manager_id)


def query_cases(soql: str, target_org: str | None) -> str:
    command = ["sf", "data", "query", "--query", soql, "--result-format", "csv"]
    if target_org:
        command.extend(["--target-org", target_org])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def summarize_cases(raw_csv_path: Path) -> tuple[int, list[dict[str, object]]]:
    owner_rows: dict[str, dict[str, object]] = defaultdict(
        lambda: {"owner_id": "", "case_count": 0},
    )
    total_cases = 0

    with raw_csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total_cases += 1
            owner_name = (row.get("Owner.Name") or "").strip() or "(Unknown owner)"
            owner = owner_rows[owner_name]
            owner["case_count"] = int(owner["case_count"]) + 1
            if not owner["owner_id"]:
                owner["owner_id"] = (row.get("OwnerId") or "").strip()

    rows = [
        {
            "owner_name": owner_name,
            "owner_id": str(info["owner_id"]),
            "case_count": int(info["case_count"]),
            "pct_total": (int(info["case_count"]) / total_cases) if total_cases else 0,
        }
        for owner_name, info in owner_rows.items()
    ]
    rows.sort(key=lambda item: (-int(item["case_count"]), str(item["owner_name"]).lower()))
    return total_cases, rows


def write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["owner_name", "owner_id", "case_count", "pct_total"],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_svg(manager_id: str, total_cases: int, rows: list[dict[str, object]]) -> str:
    width = 1400
    left_margin = 290
    right_margin = 220
    chart_width = width - left_margin - right_margin
    row_height = 34
    bar_height = 22
    top_margin = 110
    bottom_margin = 70
    height = top_margin + row_height * len(rows) + bottom_margin
    max_cases = max((int(row["case_count"]) for row in rows), default=1)
    axis_ticks = [0, max_cases * 0.25, max_cases * 0.5, max_cases * 0.75, max_cases]
    axis_ticks = [int(round(tick)) for tick in axis_ticks]

    seen: set[int] = set()
    axis_ticks = [tick for tick in axis_ticks if not (tick in seen or seen.add(tick))]

    def x_for_value(value: int) -> float:
        return left_margin + (value / max_cases) * chart_width if max_cases else left_margin

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        ),
        '<title id="title">Open non-resolved cases by owner</title>',
        (
            f'<desc id="desc">{total_cases} open non-resolved Salesforce cases for manager '
            f'{escape(manager_id)} grouped by case owner.</desc>'
        ),
        '<rect width="100%" height="100%" fill="#f8fafc" />',
        (
            f'<rect x="16" y="16" width="1368" height="{height - 32}" rx="16" '
            'fill="#ffffff" stroke="#e2e8f0"/>'
        ),
        (
            '<text x="48" y="58" font-family="Arial, Helvetica, sans-serif" '
            'font-size="28" font-weight="700" fill="#0f172a">'
            "Open Non-Resolved Cases by Owner</text>"
        ),
        (
            f'<text x="48" y="84" font-family="Arial, Helvetica, sans-serif" font-size="16" '
            f'fill="#475569">ManagerId {escape(manager_id)} '
            "• Filter: IsClosed = false AND Status != Resolved "
            f"• {total_cases:,} cases • {len(rows)} owners • Generated {escape(generated_at)}</text>"
        ),
    ]

    for tick in axis_ticks:
        x = x_for_value(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{top_margin - 16}" x2="{x:.1f}" '
            f'y2="{height - bottom_margin + 8}" stroke="#e2e8f0" stroke-width="1" />',
        )
        parts.append(
            f'<text x="{x:.1f}" y="{top_margin - 24}" text-anchor="middle" '
            'font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#64748b">'
            f"{tick:,}</text>",
        )

    bar_colors = ["#2563eb", "#0ea5e9", "#0891b2", "#0284c7"]
    for index, row in enumerate(rows):
        y = top_margin + index * row_height
        bar_y = y - (bar_height / 2)
        case_count = int(row["case_count"])
        bar_width = max(2, (case_count / max_cases) * chart_width if max_cases else 2)
        color = bar_colors[index % len(bar_colors)]
        owner_name = escape(str(row["owner_name"]))
        pct_total = float(row["pct_total"]) * 100
        value_x = left_margin + chart_width + 18
        pct_x = value_x + 50

        parts.append(
            f'<text x="48" y="{y + 5:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="14" fill="#0f172a">{owner_name}</text>',
        )
        parts.append(
            f'<rect x="{left_margin}" y="{bar_y:.1f}" width="{chart_width:.1f}" '
            f'height="{bar_height}" rx="8" fill="#e2e8f0" />',
        )
        parts.append(
            f'<rect x="{left_margin}" y="{bar_y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height}" rx="8" fill="{color}" />',
        )
        parts.append(
            f'<text x="{value_x}" y="{y + 5:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="14" font-weight="700" fill="#0f172a">{case_count:,}</text>',
        )
        parts.append(
            f'<text x="{pct_x}" y="{y + 5:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="13" fill="#475569">{pct_total:.1f}%</text>',
        )

    parts.append("</svg>")
    return "\n".join(parts)


def build_markdown(
    manager_id: str,
    total_cases: int,
    rows: list[dict[str, object]],
    raw_csv_path: Path,
    summary_csv_path: Path,
    chart_svg_path: Path,
) -> str:
    lines = [
        f"# Open non-resolved cases by owner for manager {manager_id}",
        "",
        "- Filter: `IsClosed = false AND Status != 'Resolved'`",
        f"- Total filtered cases: {total_cases:,}",
        f"- Total owners: {len(rows)}",
        f"- Raw export: `{raw_csv_path}`",
        f"- Summary CSV: `{summary_csv_path}`",
        f"- Chart: `{chart_svg_path}`",
        "",
        "| Owner | Owner ID | Cases | % Total |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['owner_name']} | {row['owner_id']} | "
            f"{int(row['case_count']):,} | {float(row['pct_total']) * 100:.1f}% |",
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    manager_id = args.manager_id
    outdir = Path(args.outdir)
    if not outdir.is_absolute():
        outdir = Path.cwd() / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    prefix = f"manager_{manager_id}_open_non_resolved"
    raw_csv_path = outdir / f"{prefix}_cases.csv"
    summary_csv_path = outdir / f"{prefix}_by_owner.csv"
    chart_svg_path = outdir / f"{prefix}_by_owner.svg"
    report_md_path = outdir / f"{prefix}_by_owner.md"

    raw_csv = query_cases(build_soql(manager_id), args.target_org)
    raw_csv_path.write_text(raw_csv, encoding="utf-8")

    total_cases, rows = summarize_cases(raw_csv_path)
    write_summary_csv(summary_csv_path, rows)
    chart_svg_path.write_text(build_svg(manager_id, total_cases, rows), encoding="utf-8")
    report_md_path.write_text(
        build_markdown(
            manager_id,
            total_cases,
            rows,
            raw_csv_path,
            summary_csv_path,
            chart_svg_path,
        ),
        encoding="utf-8",
    )

    top_owners = ", ".join(
        f"{row['owner_name']} ({int(row['case_count'])})" for row in rows[:5]
    )
    print(f"manager_id={manager_id}")
    print(f"total_cases={total_cases}")
    print(f"owners={len(rows)}")
    print(f"raw_csv={raw_csv_path}")
    print(f"summary_csv={summary_csv_path}")
    print(f"chart_svg={chart_svg_path}")
    print(f"report_md={report_md_path}")
    print(f"top_owners={top_owners}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr)
        raise
