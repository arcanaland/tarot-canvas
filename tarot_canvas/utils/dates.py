"""How a date is written for the reader, in one place.

The About dialog grew a relative-date ladder for release dates — *Today*, *Yesterday*,
*N days ago*, *N weeks ago*, and the absolute date once a release is old enough to make
"ago" useless. A note's Overview row wants exactly that, and there is no reason for the
two to drift or for the wording to be written twice.

The phrasing here is the app's existing copy, lifted from `ui/windows/about.py`.
"""

from PyQt6.QtCore import QDate, QDateTime, QLocale, Qt

# Past this, "ago" stops being informative and the date itself is more use
RELATIVE_DATE_DAYS = 30

WEEKDAY_PATTERNS = ("dddd, ", ", dddd", "dddd ", " dddd", "dddd")


def format_qdate(date):
    """`date` in the system locale's long form, without the weekday."""
    locale = QLocale.system()
    pattern = locale.dateFormat(QLocale.FormatType.LongFormat)

    for weekday in WEEKDAY_PATTERNS:
        pattern = pattern.replace(weekday, "")

    return locale.toString(date, pattern.strip())


def format_date(text):
    """An ISO date in the system locale's long form, or `text` if it isn't one."""
    date = QDate.fromString(text, Qt.DateFormat.ISODate)

    if not date.isValid():
        return text

    return format_qdate(date) or text


def relative_date(date, today=None):
    """How long ago `date` was, or the date itself once that stops being useful."""
    days = date.daysTo(QDate.currentDate() if today is None else today)

    if days < 0 or days >= RELATIVE_DATE_DAYS:
        return format_qdate(date)
    if days == 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"

    weeks = days // 7
    return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"


def relative_date_from_iso(iso, today=None):
    """`relative_date` for an ISO string, which is returned unchanged if it isn't one."""
    date = QDate.fromString(iso, Qt.DateFormat.ISODate)

    if not date.isValid():
        return iso

    return relative_date(date, today)


def relative_date_from_timestamp(seconds, today=None):
    """`relative_date` for a file's modification time."""
    return relative_date(QDateTime.fromSecsSinceEpoch(int(seconds)).date(), today)
