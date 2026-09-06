"""The deck view page: an inline header where a modal dialog used to be."""

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QLabel

from tarot_canvas.ui.tabs import deck_view_tab as module
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.widgets.deck_header import DeckHeader
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def tab(qtbot):
    widget = DeckViewTab(str(MINIMAL_DECK_PATH))
    qtbot.addWidget(widget)
    return widget


def test_the_deck_view_has_a_deck_level_header(tab):
    headers = tab.findChildren(DeckHeader)
    assert len(headers) == 1
    assert headers[0].title_label.text() == "Minimal Test Deck"


def test_nothing_in_the_deck_view_opens_a_dialog(tab):
    """RFC-021 defect 1: four lines of read-only text is not a reason to go modal."""
    assert not hasattr(tab, "show_deck_info")
    assert not hasattr(module, "DeckInfoDialog")
    assert tab.findChildren(QDialog) == []


def test_the_header_reaches_the_edges_of_the_view(tab, qtbot):
    """The banner is a page header; an inset would make it read as a floating bar."""
    qtbot.addWidget(tab)
    tab.resize(900, 600)
    tab.show()
    qtbot.waitExposed(tab)
    header = tab.findChildren(DeckHeader)[0]
    assert header.mapTo(tab, QPoint(0, 0)).x() == 0
    assert header.mapTo(tab, QPoint(0, 0)).y() == 0


def test_the_sections_take_back_the_margin_the_header_gave_up(tab, qtbot):
    """With the tab flush, section titles would otherwise sit against the window edge."""
    qtbot.addWidget(tab)
    tab.resize(900, 600)
    tab.show()
    qtbot.waitExposed(tab)
    titles = [label for label in tab.findChildren(QLabel) if label.text() == "Major Arcana"]
    assert titles, "the fixture deck renders a Major Arcana section"
    assert titles[0].mapTo(tab, QPoint(0, 0)).x() == module.SECTION_MARGIN


def test_section_titles_use_the_system_font(tab):
    title = tab.section_title("Major Arcana")
    assert title.font().family() == QApplication.font().family()
    assert title.font().bold()
    assert title.font().pointSizeF() > QApplication.font().pointSizeF()


def test_no_widget_in_the_deck_view_hardcodes_a_colour(tab):
    for label in tab.findChildren(QLabel):
        assert label.styleSheet() == ""


def test_the_exclusion_note_is_palette_derived(tab):
    """The minimal fixture excludes 76 cards, so it renders the note."""
    notes = [
        label
        for label in tab.findChildren(QLabel)
        if label.text().startswith("Note: Test fixture only needs")
    ]
    assert len(notes) == 1
    assert notes[0].foregroundRole() == QPalette.ColorRole.PlaceholderText
    assert notes[0].font().italic()
