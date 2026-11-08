from PyQt6.QtCore import QDate, QDateTime, QLocale, Qt

from tarot_canvas.ui.strings import DATES, READINGS

RELATIVE_DATE_DAYS = 30

WEEKDAY_PATTERNS = ("dddd, ", ", dddd", "dddd ", " dddd", "dddd")


def format_qdate(date):
    """`date` in the system locale's long form, without the weekday."""
    locale = QLocale.system()
    pattern = locale.dateFormat(QLocale.FormatType.LongFormat)

    for weekday in WEEKDAY_PATTERNS:
        pattern = pattern.replace(weekday, "")

    return locale.toString(date, pattern.strip())


def format_qdatetime(datetime):
    """`datetime`'s date as `format_qdate` writes it, then its time in the locale's short form."""
    time = QLocale.system().toString(datetime.time(), QLocale.FormatType.ShortFormat)
    return READINGS["date_and_time"].format(date=format_qdate(datetime.date()), time=time)


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
        return DATES["today"]
    if days == 1:
        return DATES["yesterday"]
    if days < 7:
        return DATES["days_ago"].format(days=days)

    weeks = days // 7
    return DATES["week_ago"] if weeks == 1 else DATES["weeks_ago"].format(weeks=weeks)


def relative_date_from_iso(iso, today=None):
    """`relative_date` for an ISO string, which is returned unchanged if it isn't one."""
    date = QDate.fromString(iso, Qt.DateFormat.ISODate)

    if not date.isValid():
        return iso

    return relative_date(date, today)


def relative_date_from_timestamp(seconds, today=None):
    """`relative_date` for a file's modification time."""
    return relative_date(QDateTime.fromSecsSinceEpoch(int(seconds)).date(), today)
