import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "flathub_stats.py"


@pytest.fixture(scope="module")
def stats():
    spec = importlib.util.spec_from_file_location("flathub_stats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve string annotations through sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


def d(month, day):
    return date(2026, month, day)


def updates_only(n):
    return {"x86_64": [n, n]}


def test_same_day_commits_collapse(stats):
    commits = [
        stats.Commit(d(10, 9), "a"),
        stats.Commit(d(10, 9), "b"),
        stats.Commit(d(10, 10), "c"),
    ]
    days = {d(10, n): updates_only(1) for n in range(9, 14)}

    rows = stats.windows(commits, days)

    assert [(w.start, w.label, w.days) for w in rows] == [
        (d(10, 9), "a + b", 1),
        (d(10, 10), "c", 4),
    ]


def test_a_window_under_three_days_has_no_3_day_updates(stats):
    commits = [stats.Commit(d(9, 3), "short"), stats.Commit(d(9, 5), "long")]
    days = {d(9, n): updates_only(10) for n in range(3, 10)}

    short, long = stats.windows(commits, days)

    assert short.days == 2 and short.updates_3d is None
    assert long.updates_3d == 30 and long.updates == 50
    assert "short" in stats.format_table([short]).splitlines()[1]


def test_fresh_is_downloads_less_updates_over_every_arch(stats):
    commits = [stats.Commit(d(11, 1), "x")]
    days = {d(11, 1): {"x86_64": [23, 13], "aarch64": [4, 1]}}

    (row,) = stats.windows(commits, days)

    assert row.updates == 14
    assert row.fresh == 13


def test_an_absent_or_missing_day_counts_zero(stats):
    commits = [stats.Commit(d(11, 1), "x"), stats.Commit(d(11, 5), "y")]
    days = {d(11, 1): updates_only(5), d(11, 2): {}, d(11, 5): updates_only(1)}

    first, _ = stats.windows(commits, days)

    assert first.days == 4
    assert first.updates == 5
    assert first.updates_3d == 5
    assert first.fresh == 0


def test_the_last_window_is_open_to_the_newest_day(stats):
    commits = [stats.Commit(d(11, 5), "1.8.0"), stats.Commit(d(11, 12), "1.9.0")]
    days = {d(11, n): updates_only(1) for n in range(5, 16)}

    rows = stats.windows(commits, days)

    assert [w.open for w in rows] == [False, True]
    assert rows[-1].days == 4
    assert "4 (open)" in stats.format_table(rows)


def test_windows_before_since_are_dropped_not_truncated(stats):
    commits = [stats.Commit(d(8, 25), "old"), stats.Commit(d(9, 6), "new")]
    days = {d(9, n): updates_only(1) for n in range(1, 10)}

    rows = stats.windows(commits, days, since=d(9, 1))

    assert [w.label for w in rows] == ["new"]


def test_label_is_the_first_line_trimmed(stats):
    assert stats.label("Update tarot-canvas to 1.8.0 (#33)\n\nbody") == (
        "Update tarot-canvas to 1.8.0 (#33)"
    )
    assert len(stats.label("x" * 80)) == stats.LABEL_CHARS


def test_deck_lines_show_the_change_only_after_a_previous_run(stats):
    counts = {"rider-waite-smith-1.1.zip": 1201, "marseille-1.0.tarotdeck": 32}

    first = stats.format_decks(counts, None)
    later = stats.format_decks(counts, {"rider-waite-smith-1.1.zip": 1190})

    assert "+" not in first
    assert later.splitlines()[0].endswith("+11")
    assert later.splitlines()[1].endswith("32")


def test_window_rates_leave_out_days_flathub_could_not_serve(stats):
    commits = [stats.Commit(d(11, 1), "x"), stats.Commit(d(11, 5), "y")]
    days = {d(11, 1): {"x86_64": [12, 10]}, d(11, 2): {"x86_64": [6, 4]}, d(11, 5): {}}

    first, _ = stats.windows(commits, days)

    assert first.days == 4 and first.measured == 2
    assert first.updates_per_day == 7.0
    assert first.fresh_per_day == 2.0


def test_the_summary_averages_each_span_back_from_the_newest_day(stats):
    days = {d(11, n): {"x86_64": [n + 1, n]} for n in range(1, 31)}

    rows = stats.periods(days, first=d(11, 1))

    assert [p.span for p in rows] == [7, 30]
    week, month = rows
    assert week.updates_per_day == sum(range(24, 31)) / 7
    assert week.fresh_per_day == 1.0
    assert month.updates_per_day == sum(range(1, 31)) / 30


def test_the_summary_table_has_one_row_per_span(stats):
    text = stats.format_summary([stats.Period(7, 8.57, 54.14)])

    assert text.splitlines()[1].split() == ["last", "7", "days", "8.6", "54.1"]
