import pytest
from PyQt6.QtCore import QDate, QDateTime

from tarot_canvas.utils.dates import (
    RELATIVE_DATE_DAYS,
    format_date,
    format_qdate,
    relative_date,
    relative_date_from_iso,
    relative_date_from_timestamp,
)

TODAY = QDate(2026, 9, 21)


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, "Today"),
        (1, "Yesterday"),
        (2, "2 days ago"),
        (6, "6 days ago"),
        (7, "1 week ago"),
        (13, "1 week ago"),
        (14, "2 weeks ago"),
        (29, "4 weeks ago"),
    ],
)
def test_the_ladder_reads_the_way_the_about_dialog_always_did(qtbot, days_ago, expected):
    assert relative_date(TODAY.addDays(-days_ago), TODAY) == expected


def test_an_old_date_stops_saying_ago_and_shows_itself(qtbot):
    old = TODAY.addDays(-RELATIVE_DATE_DAYS)

    assert relative_date(old, TODAY) == format_qdate(old)


def test_a_date_in_the_future_shows_itself_rather_than_a_negative_age(qtbot):
    ahead = TODAY.addDays(3)

    assert relative_date(ahead, TODAY) == format_qdate(ahead)


def test_a_string_that_is_not_a_date_comes_back_unchanged(qtbot):
    assert relative_date_from_iso("sometime", TODAY) == "sometime"
    assert format_date("sometime") == "sometime"


def test_an_iso_date_goes_through_the_same_ladder(qtbot):
    assert relative_date_from_iso("2026-09-20", TODAY) == "Yesterday"


def test_a_file_time_goes_through_the_same_ladder(qtbot):
    yesterday = QDateTime(TODAY.addDays(-1).startOfDay()).toSecsSinceEpoch()

    assert relative_date_from_timestamp(yesterday, TODAY) == "Yesterday"


def test_an_iso_string_and_its_qdate_render_identically(qtbot):
    assert format_date("2020-01-15") == format_qdate(QDate(2020, 1, 15))


def test_the_weekday_is_stripped_from_whatever_the_locale_offers(qtbot):
    from PyQt6.QtCore import QLocale

    locale = QLocale.system()
    full = locale.toString(QDate(2020, 1, 15), QLocale.FormatType.LongFormat)
    weekday = locale.dayName(QDate(2020, 1, 15).dayOfWeek())

    rendered = format_qdate(QDate(2020, 1, 15))

    assert weekday not in rendered
    assert len(rendered) <= len(full)
