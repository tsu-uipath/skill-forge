#!/usr/bin/env python3

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass


BROWSER_ALIASES = {
    "brave": "Brave Browser",
    "brave-browser": "Brave Browser",
    "chrome": "Google Chrome",
    "chromium": "Chromium",
    "edge": "Microsoft Edge",
    "google-chrome": "Google Chrome",
    "microsoft-edge": "Microsoft Edge",
    "safari": "Safari",
}


LIST_SCRIPT_TEMPLATE = """
if application "{app_name}" is not running then error "Browser is not running: {app_name}"

using terms from application "{app_name}"
  tell application "{app_name}"
    set outText to ""
    set fieldSeparator to ASCII character 9
    repeat with w from 1 to count of windows
      repeat with t from 1 to count of tabs of window w
        set currentTab to tab t of window w
        set tabTitle to ""
        set tabUrl to ""
        try
          set tabTitle to title of currentTab
        on error
          try
            set tabTitle to name of currentTab
          end try
        end try
        try
          set tabUrl to URL of currentTab
        end try
        set flatTitle to do shell script "printf %s " & quoted form of tabTitle & " | tr '\\r\\n\\t' '   '"
        set flatUrl to do shell script "printf %s " & quoted form of tabUrl & " | tr '\\r\\n\\t' '   '"
        set outText to outText & w & fieldSeparator & t & fieldSeparator & flatTitle & fieldSeparator & flatUrl & linefeed
      end repeat
    end repeat
    return outText
  end tell
end using terms from
""".strip()


@dataclass(frozen=True)
class TabRecord:
    window_index: int
    tab_index: int
    title: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Close matching tabs in a macOS browser application.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 close_tabs.py --browser edge --pattern grubhub --pattern microsoft\n"
            "  python3 close_tabs.py --browser chrome --pattern docs.google.com --field url\n"
            "  python3 close_tabs.py --browser safari --pattern 'Sign in' --mode exact --dry-run"
        ),
    )
    parser.add_argument(
        "--browser",
        required=True,
        help="Browser alias (edge, chrome, brave, chromium, safari) or exact macOS app name.",
    )
    parser.add_argument(
        "--pattern",
        "--tab",
        action="append",
        dest="patterns",
        required=True,
        help="Tab text to match. Repeat for multiple patterns.",
    )
    parser.add_argument(
        "--field",
        choices=("title", "url", "either"),
        default="either",
        help="Where to search for each pattern. Default: either.",
    )
    parser.add_argument(
        "--mode",
        choices=("contains", "exact", "regex"),
        default="contains",
        help="Pattern match mode. Default: contains.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matches without closing any tabs.",
    )
    return parser.parse_args()


def resolve_browser(browser: str) -> str:
    return BROWSER_ALIASES.get(browser.strip().lower(), browser.strip())


def run_osascript(script: str) -> str:
    command = ["osascript"]
    for line in script.splitlines():
        if not line.strip():
            continue
        command.extend(["-e", line])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Unknown AppleScript error"
        raise RuntimeError(message)
    return result.stdout


def list_tabs(app_name: str) -> list[TabRecord]:
    output = run_osascript(LIST_SCRIPT_TEMPLATE.format(app_name=app_name))
    tabs: list[TabRecord] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        if len(parts) != 4:
            continue
        window_index, tab_index, title, url = parts
        tabs.append(
            TabRecord(
                window_index=int(window_index),
                tab_index=int(tab_index),
                title=title,
                url=url,
            )
        )
    return tabs


def build_matchers(patterns: list[str], mode: str):
    if mode == "contains":
        lowered = [pattern.lower() for pattern in patterns]

        def matcher(value: str) -> bool:
            candidate = value.lower()
            return any(pattern in candidate for pattern in lowered)

        return matcher

    if mode == "exact":
        lowered = [pattern.lower() for pattern in patterns]

        def matcher(value: str) -> bool:
            return value.lower() in lowered

        return matcher

    regexes = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    def matcher(value: str) -> bool:
        return any(regex.search(value) for regex in regexes)

    return matcher


def is_match(tab: TabRecord, field: str, matcher) -> bool:
    if field == "title":
        return matcher(tab.title)
    if field == "url":
        return matcher(tab.url)
    return matcher(tab.title) or matcher(tab.url)


def close_tabs(app_name: str, tabs: list[TabRecord]) -> None:
    lines = [f'if application "{app_name}" is not running then error "Browser is not running: {app_name}"']
    lines.append(f'using terms from application "{app_name}"')
    lines.append(f'  tell application "{app_name}"')
    for tab in sorted(tabs, key=lambda item: (item.window_index, item.tab_index), reverse=True):
        lines.append("    try")
        lines.append(f"      close tab {tab.tab_index} of window {tab.window_index}")
        lines.append("    end try")
    lines.append("  end tell")
    lines.append("end using terms from")
    run_osascript("\n".join(lines))


def print_matches(app_name: str, tabs: list[TabRecord], dry_run: bool) -> None:
    action = "Would close" if dry_run else "Closed"
    print(f"{action} {len(tabs)} tab(s) in {app_name}:")
    for tab in tabs:
        print(
            f"- window {tab.window_index}, tab {tab.tab_index}: "
            f"{tab.title or '[no title]'} | {tab.url or '[no url]'}"
        )


def main() -> int:
    args = parse_args()
    app_name = resolve_browser(args.browser)

    try:
        tabs = list_tabs(app_name)
        matcher = build_matchers(args.patterns, args.mode)
        matches = [tab for tab in tabs if is_match(tab, args.field, matcher)]
        if not matches:
            print(f"No matching tabs found in {app_name}.")
            return 0

        if args.dry_run:
            print_matches(app_name, matches, dry_run=True)
            return 0

        close_tabs(app_name, matches)
        print_matches(app_name, matches, dry_run=False)
        return 0
    except re.error as error:
        print(f"Invalid regex: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
