#!/usr/bin/env python3
"""Print Flathub install/update stats and deck download counts"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

APP_ID = "land.arcana.TarotCanvas"
FLATHUB_REPO = f"flathub/{APP_ID}"
DECKS_REPO = "arcanaland/reference-decks"

DAY_URL = "https://flathub.org/stats/{d:%Y}/{d:%m}/{d:%d}.json"
STATS_URL = f"https://flathub.org/api/v2/stats/{APP_ID}"
COMMITS_URL = f"https://api.github.com/repos/{FLATHUB_REPO}/commits?sha=master&per_page=100"
RELEASES_URL = f"https://api.github.com/repos/{DECKS_REPO}/releases?per_page=100"

DEFAULT_SPAN_DAYS = 90
# A day's file is final once Flathub has stopped appending to it
FINAL_AFTER_DAYS = 2
DAY_FILE_MB = 15
WARN_UNCACHED_DAYS = 10
WORKERS = 8
FIRST_DAYS = 3
LABEL_CHARS = 50
TIMEOUT = 60
USER_AGENT = "tarot-canvas-flathub-stats"

SUMMARY_SPANS = (7, 30, 90)
SUMMARY_COLUMNS = ("", "fresh/day", "updates/day")
COLUMNS = ("publish", "days", "3-day updates", "updates/day", "fresh/day", "label")

# arch -> [downloads, updates]; {} when the app is absent that day
Day = dict[str, list[int]]


@dataclass(frozen=True)
class Commit:
    day: date
    label: str


@dataclass(frozen=True)
class Window:
    start: date
    days: int
    updates: int
    updates_3d: int | None
    fresh: int
    label: str
    open: bool = False
    # Days with data; a day Flathub couldn't serve is left out of the rates
    measured: int = 0

    @property
    def updates_per_day(self) -> float | None:
        return self.updates / self.measured if self.measured else None

    @property
    def fresh_per_day(self) -> float | None:
        return self.fresh / self.measured if self.measured else None


@dataclass(frozen=True)
class Period:
    span: int
    fresh_per_day: float
    updates_per_day: float


def rate(value: float | None) -> str:
    return "" if value is None else f"{value:.1f}"


def periods(days: dict[date, Day], first: date, spans=SUMMARY_SPANS) -> list[Period]:
    """Per-day averages over the last N days to the newest day, for each span
    the fetched range covers; days without data are left out of the average"""
    if not days:
        return []
    end = max(days)
    result = []
    for span in spans:
        start = end - timedelta(days=span - 1)
        if start < first:
            continue
        present = [totals(day) for d, day in days.items() if start <= d <= end]
        if not present:
            continue
        result.append(
            Period(
                span,
                fresh_per_day=sum(f for _, f in present) / len(present),
                updates_per_day=sum(u for u, _ in present) / len(present),
            )
        )
    return result


def _align(cells: list[list[str]]) -> str:
    """First column left, last column left and unpadded, the rest right-aligned"""
    widths = [max(len(row[i]) for row in cells) for i in range(len(cells[0]))]
    lines = []
    for row in cells:
        parts = [row[0].ljust(widths[0])]
        parts += [row[i].rjust(widths[i]) for i in range(1, len(row) - 1)]
        parts.append(row[-1] if len(row) > 1 else "")
        lines.append("  ".join(parts).rstrip())
    return "\n".join(lines)


def format_summary(rows: list[Period]) -> str:
    cells = [list(SUMMARY_COLUMNS) + [""]]
    for period in rows:
        cells.append(
            [
                f"last {period.span} days",
                rate(period.fresh_per_day),
                rate(period.updates_per_day),
                "",
            ]
        )
    return _align(cells)


def label(message: str) -> str:
    """First line of a commit message, trimmed"""
    first = message.strip().splitlines()[0].strip() if message.strip() else ""
    return first if len(first) <= LABEL_CHARS else first[: LABEL_CHARS - 1] + "…"


def totals(day: Day) -> tuple[int, int]:
    """(updates, fresh installs) summed over arches; fresh = downloads - updates"""
    downloads = sum(pair[0] for pair in day.values())
    updates = sum(pair[1] for pair in day.values())
    return updates, downloads - updates


def windows(
    commits: list[Commit], days: dict[date, Day], since: date | None = None
) -> list[Window]:
    """One window per publish day, running to the day before the next."""
    by_day: dict[date, list[str]] = {}
    for commit in sorted(commits, key=lambda c: c.day):
        by_day.setdefault(commit.day, []).append(commit.label)
    starts = sorted(by_day)
    last_day = max(days) if days else None

    result = []
    for i, start in enumerate(starts):
        is_open = i == len(starts) - 1
        if is_open:
            if last_day is None:
                break
            end = last_day
        else:
            end = starts[i + 1] - timedelta(days=1)
        if since is not None and start < since:
            continue
        length = max((end - start).days + 1, 0)
        span = [start + timedelta(days=n) for n in range(length)]
        per_day = [totals(days.get(d, {})) for d in span]
        result.append(
            Window(
                start=start,
                days=length,
                updates=sum(u for u, _ in per_day),
                updates_3d=sum(u for u, _ in per_day[:FIRST_DAYS])
                if length >= FIRST_DAYS
                else None,
                fresh=sum(f for _, f in per_day),
                label=" + ".join(by_day[start]),
                open=is_open,
                measured=sum(1 for d in span if d in days),
            )
        )
    return result


def format_table(rows: list[Window]) -> str:
    """Plain aligned text, numbers right-aligned"""
    cells = [list(COLUMNS)]
    for w in rows:
        cells.append(
            [
                w.start.isoformat(),
                f"{w.days} (open)" if w.open else str(w.days),
                "" if w.updates_3d is None else str(w.updates_3d),
                rate(w.updates_per_day),
                rate(w.fresh_per_day),
                w.label,
            ]
        )
    return _align(cells)


def format_decks(counts: dict[str, int], previous: dict[str, int] | None) -> str:
    """One line per asset: name, count, change since the previous run"""
    if not counts:
        return ""
    name_width = max(len(name) for name in counts)
    count_width = max(len(str(n)) for n in counts.values())
    lines = []
    for name, count in counts.items():
        line = f"{name.ljust(name_width)}  {str(count).rjust(count_width)}"
        if previous is not None and name in previous:
            line += f"  {count - previous[name]:+d}"
        lines.append(line)
    return "\n".join(lines)


# -- I/O ----------------------------------------------------------------------


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "tarot-canvas" / "flathub-stats"


def _request(url: str, github: bool = False) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    if github:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def get_json(url: str, github: bool = False):
    with urllib.request.urlopen(_request(url, github), timeout=TIMEOUT) as response:
        return json.load(response)


def get_paged(url: str) -> list:
    """Every page of a GitHub list endpoint, following Link: rel="next" """
    items: list = []
    next_url: str | None = url
    while next_url:
        with urllib.request.urlopen(_request(next_url, github=True), timeout=TIMEOUT) as response:
            items += json.load(response)
            links = response.headers.get("Link") or ""
        match = re.search(r'<([^>]+)>;\s*rel="next"', links)
        next_url = match.group(1) if match else None
    return items


def fetch_commits() -> list[Commit]:
    commits = []
    # GitHub lists newest first; same-day labels read in the order they landed
    for item in reversed(get_paged(COMMITS_URL)):
        stamp = datetime.fromisoformat(item["commit"]["committer"]["date"].replace("Z", "+00:00"))
        commits.append(Commit(stamp.astimezone(UTC).date(), label(item["commit"]["message"])))
    return commits


def fetch_day(day: date) -> Day:
    """The app's entry in one day's stats file"""
    data = get_json(DAY_URL.format(d=day))
    return {arch: list(pair) for arch, pair in data.get("refs", {}).get(APP_ID, {}).items()}


def load_days(wanted: list[date], today: date, refresh: bool) -> tuple[dict[date, Day], list[date]]:
    """Days from the cache or Flathub, and the days that could not be had"""
    folder = cache_dir() / "days"
    days: dict[date, Day] = {}
    if not refresh:
        for day in wanted:
            path = folder / f"{day.isoformat()}.json"
            if path.exists():
                days[day] = json.loads(path.read_text())
    todo = [day for day in wanted if day not in days]

    if len(todo) > WARN_UNCACHED_DAYS:
        print(
            f"{len(todo)} days uncached: about {len(todo) * DAY_FILE_MB / 1000:.1f} GB to download",
            file=sys.stderr,
        )

    final = today - timedelta(days=FINAL_AFTER_DAYS)
    missing = []

    def one(day: date) -> tuple[date, Day | None, str]:
        try:
            return day, fetch_day(day), ""
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return day, None, str(exc)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, (day, entry, error) in enumerate(pool.map(one, todo), 1):
            if entry is None:
                print(f"{day}: {error}", file=sys.stderr)
                missing.append(day)
                continue
            days[day] = entry
            if day <= final:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{day.isoformat()}.json").write_text(json.dumps(entry))
            print(f"fetched {done}/{len(todo)} days", file=sys.stderr)
    return days, sorted(missing)


def fetch_deck_counts() -> dict[str, int]:
    return {
        asset["name"]: asset["download_count"]
        for release in get_paged(RELEASES_URL)
        for asset in release.get("assets", [])
    }


def previous_deck_counts() -> dict[str, int] | None:
    path = cache_dir() / "decks.json"
    try:
        return json.loads(path.read_text())["counts"]
    except (OSError, ValueError, KeyError):
        return None


def save_deck_counts(counts: dict[str, int], today: date) -> None:
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "decks.json").write_text(json.dumps({"date": today.isoformat(), "counts": counts}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        help=f"first publish day to show, YYYY-MM-DD (default: {DEFAULT_SPAN_DAYS} days ago)",
    )
    parser.add_argument("--refresh", action="store_true", help="ignore the cached days")
    args = parser.parse_args(argv)

    today = datetime.now(UTC).date()
    since = args.since or today - timedelta(days=DEFAULT_SPAN_DAYS)

    try:
        stats = get_json(STATS_URL)
        commits = fetch_commits()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"flathub_stats: cannot reach Flathub or GitHub: {exc}", file=sys.stderr)
        return 1

    print(
        f"installs_total {stats.get('installs_total')}"
        f"  installs_last_month {stats.get('installs_last_month')}"
        f"  installs_last_7_days {stats.get('installs_last_7_days')}"
    )
    print()

    # The summary's longest span ends yesterday, whatever --since says
    first = min(since, today - timedelta(days=max(SUMMARY_SPANS)))
    wanted = [first + timedelta(days=n) for n in range((today - first).days)]
    days, missing = load_days(wanted, today, args.refresh)
    print(format_summary(periods(days, first)))
    print()
    print(format_table(windows(commits, days, since)))
    if missing:
        print(f"missing days: {', '.join(d.isoformat() for d in missing)}", file=sys.stderr)

    try:
        counts = fetch_deck_counts()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"deck counts unavailable: {exc}", file=sys.stderr)
    else:
        print()
        print(format_decks(counts, previous_deck_counts()))
        save_deck_counts(counts, today)

    return 0


if __name__ == "__main__":
    sys.exit(main())
