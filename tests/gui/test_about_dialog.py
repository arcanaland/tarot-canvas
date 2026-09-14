import pytest
from PyQt6.QtCore import QDate, QLocale, Qt

from tarot_canvas._version import __version__
from tarot_canvas.about import AboutData, Release, load_about_data
from tarot_canvas.ui.widgets.deck_header import format_date
from tarot_canvas.ui.windows.about import AboutDialog, _release_date


def _tab_titles(dialog):
    return [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]


def _tab_text(dialog, title):
    index = _tab_titles(dialog).index(title)
    page = dialog.tabs.widget(index)
    from PyQt6.QtWidgets import QLabel

    return "\n".join(label.text() for label in page.findChildren(QLabel))


@pytest.fixture
def dialog(qtbot):
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_header_has_version(dialog):
    assert __version__ in dialog.version_label.text()


def test_authors_tab_has_url(dialog):
    bugtracker = load_about_data().bugtracker

    assert bugtracker
    assert bugtracker in _tab_text(dialog, "Authors")


def test_authors_tab_lists_the_maintainer_with_a_role(dialog):
    text = _tab_text(dialog, "Authors")

    assert "Adam Fidel" in text
    assert "Maintainer" in text


def test_about_tab_shows_the_metainfo_summary(dialog):
    assert load_about_data().summary in _tab_text(dialog, "About")


def test_tabs_for_the_bundled_metainfo(dialog):
    assert _tab_titles(dialog) == ["About", "What's New", "Authors"]


def test_whats_new_has_notes_for_the_running_version(dialog):
    # Fails after a version bump until that version's <release> entry is written
    assert __version__ in dialog.whats_new.toPlainText()


RELEASES = (
    Release("1.5.0", "2020-02-01", "development", "<p>Not out yet.</p>"),
    Release("1.4.1", "2020-01-15", "stable", "<ul><li>Out now.</li></ul>"),
)


def _dialog_for(qtbot, releases=RELEASES):
    dialog = AboutDialog(about=AboutData(version="1.4.1", releases=releases))
    qtbot.addWidget(dialog)
    return dialog


def test_whats_new_shows_a_release_ahead_of_the_running_version(qtbot):
    # Bound, or the dialog is collected and takes its QTextBrowser with it
    dialog = _dialog_for(qtbot)
    text = dialog.whats_new.toPlainText()

    positions = [text.index(s) for s in ("1.5.0", "Not out yet.", "1.4.1", "Out now.")]
    assert positions == sorted(positions)


def test_no_whats_new_tab_without_releases(qtbot):
    dialog = _dialog_for(qtbot, releases=())

    assert _tab_titles(dialog) == ["About", "Authors"]
    assert dialog.whats_new is None


def test_whats_new_shows_a_recent_date_as_time_ago(qtbot):
    two_weeks_ago = QDate.currentDate().addDays(-14).toString(Qt.DateFormat.ISODate)
    dialog = _dialog_for(qtbot, releases=(Release("1.4.1", two_weeks_ago),))

    assert "2 weeks ago" in dialog.whats_new.toPlainText()


def test_whats_new_shows_an_old_date_without_its_weekday(qtbot):
    dialog = _dialog_for(qtbot)
    text = dialog.whats_new.toPlainText()

    assert format_date("2020-01-15") in text
    assert QLocale.system().dayName(QDate(2020, 1, 15).dayOfWeek()) not in text


TODAY = QDate(2026, 9, 14)


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        ("2026-09-14", "Today"),
        ("2026-09-13", "Yesterday"),
        ("2026-09-11", "3 days ago"),
        ("2026-09-07", "1 week ago"),
        ("2026-08-31", "2 weeks ago"),
        ("2026-08-16", "4 weeks ago"),
    ],
)
def test_a_date_within_a_month_reads_as_time_ago(iso, expected):
    assert _release_date(iso, TODAY) == expected


@pytest.mark.parametrize("iso", ["2026-08-15", "2025-12-25", "2026-09-20"])
def test_an_older_or_future_date_is_shown_as_a_date(iso):
    assert _release_date(iso, TODAY) == format_date(iso)


def test_an_unparseable_date_is_shown_as_written():
    assert _release_date("sometime", TODAY) == "sometime"


def test_whats_new_follows_a_palette_change(qtbot):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPalette

    dialog = _dialog_for(qtbot)
    role = QPalette.ColorRole.PlaceholderText
    palette = dialog.palette()
    palette.setColor(role, Qt.GlobalColor.darkMagenta)
    dialog.setPalette(palette)

    assert dialog.palette().color(role).name() in dialog.whats_new.toHtml()


def test_opens_when_the_metainfo_cannot_be_parsed(qtbot, monkeypatch, caplog):
    import tarot_canvas.about as about_module

    def explode(*args, **kwargs):
        raise OSError("no metainfo here")

    monkeypatch.setattr(about_module, "files", explode)

    data = load_about_data()
    assert data == AboutData()

    dialog = AboutDialog(about=data)
    qtbot.addWidget(dialog)
    assert _tab_titles(dialog) == ["About", "Authors"]
    assert about_module.FALLBACK_SUMMARY in _tab_text(dialog, "About")
