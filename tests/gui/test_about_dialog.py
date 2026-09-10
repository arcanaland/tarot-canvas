"""The about dialog. RFC-031.

It takes its data from `tarot_canvas.about` and touches no deck, so -- unlike
`MainWindow` -- it can be built without `deck_manager` and without the first-launch
reference-deck fetch.
"""

import pytest

from tarot_canvas._version import __version__
from tarot_canvas.about import AboutData, load_about_data
from tarot_canvas.ui.windows.about import AboutDialog


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


def test_title_echoes_the_menu_item(dialog):
    assert dialog.windowTitle() == "About Tarot Canvas"


def test_three_tabs_in_kde_order(dialog):
    assert _tab_titles(dialog) == ["About", "Components", "Authors"]


def test_header_carries_the_version(dialog):
    assert __version__ in dialog.version_label.text()


def test_authors_tab_carries_the_bugtracker_url(dialog):
    bugtracker = load_about_data().bugtracker

    assert bugtracker
    assert bugtracker in _tab_text(dialog, "Authors")


def test_authors_tab_lists_the_maintainer_with_a_role(dialog):
    text = _tab_text(dialog, "Authors")

    assert "Adam Fidel" in text
    assert "Maintainer" in text


def test_the_author_row_offers_an_email_button(dialog, monkeypatch):
    """Gwenview puts a mail button on each author row; the address is in the metainfo."""
    from PyQt6.QtWidgets import QToolButton

    from tarot_canvas.ui.windows import about as about_dialog_module

    opened = []
    monkeypatch.setattr(
        about_dialog_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()),
    )

    index = _tab_titles(dialog).index("Authors")
    buttons = dialog.tabs.widget(index).findChildren(QToolButton)
    assert len(buttons) == 1

    buttons[0].click()
    assert opened == [f"mailto:{load_about_data().contact}"]


def test_a_person_without_an_email_gets_no_button(qtbot):
    from PyQt6.QtWidgets import QToolButton

    data = AboutData(contact=None)
    dialog = AboutDialog(about=data)
    qtbot.addWidget(dialog)

    index = _tab_titles(dialog).index("Authors")
    assert dialog.tabs.widget(index).findChildren(QToolButton) == []


def test_about_tab_shows_the_metainfo_summary(dialog):
    assert load_about_data().summary in _tab_text(dialog, "About")


def test_components_tab_lists_the_runtime(dialog):
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

    text = _tab_text(dialog, "Components")
    assert QT_VERSION_STR in text
    assert PYQT_VERSION_STR in text


def test_opens_when_the_metainfo_cannot_be_parsed(qtbot, monkeypatch, caplog):
    """A bad resource must not be the thing that stops the about box from opening."""
    import tarot_canvas.about as about_module

    def explode(*args, **kwargs):
        raise OSError("no metainfo here")

    monkeypatch.setattr(about_module, "files", explode)

    data = load_about_data()
    assert data == AboutData()

    dialog = AboutDialog(about=data)
    qtbot.addWidget(dialog)
    assert _tab_titles(dialog) == ["About", "Components", "Authors"]
    assert about_module.FALLBACK_SUMMARY in _tab_text(dialog, "About")
