"""New Reading is one spread menu, in File, the + menu and the Welcome tab."""

import os

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton

from tarot_canvas.models import spreads
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import LIBRARY_VIEW_SPREADS
from tarot_canvas.ui.canvas.placement import Phase
from tarot_canvas.ui.library.tab import LibraryTab
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.spread_menu import MAX_OWN
from tarot_canvas.ui.strings import MAIN_WINDOW, READINGS
from tarot_canvas.ui.tabs.reading_tab import ReadingTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab


def with_slots(name, count):
    return Spread(name=name, positions=tuple(Position(id=f"p{n}") for n in range(1, count + 1)))


def save(base, folder, name, edited, count=1):
    path = base / folder
    path.mkdir(parents=True)
    spreads.save(path, with_slots(name, count))
    os.utime(path / spreads.SPREAD_FILE, (edited, edited))
    return path


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    """A window left with unsaved work would otherwise wait on a dialog as it closes"""
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def filled(menu):
    menu.aboutToShow.emit()
    return menu


def entries(menu):
    return [None if action.isSeparator() else action.text() for action in menu.actions()]


def entry(menu, text):
    return next(action for action in menu.actions() if action.text() == text)


def test_the_users_newest_then_included_smallest_first_then_browse(
    window, included_base, spreads_base
):
    save(included_base, "cross", "Celtic Cross", 1, count=10)
    save(included_base, "three", "Three Card", 1, count=3)
    save(included_base, "single", "Single Card", 1, count=1)
    save(included_base, "past", "Past Present Future", 1, count=3)  # a tie goes by name
    save(spreads_base, "old", "Old", 100)
    save(spreads_base, "new", "New", 200)

    assert entries(filled(window.new_reading_menu)) == [
        "New",
        "Old",
        None,
        "Single Card",
        "Past Present Future",
        "Three Card",
        "Celtic Cross",
        None,
        READINGS["browse_spreads"],
    ]


def test_only_the_users_newest_few_are_listed(window, spreads_base):
    for n in range(MAX_OWN + 2):
        save(spreads_base, f"s{n}", f"Mine {n}", 100 + n)

    names = [text for text in entries(filled(window.new_reading_menu)) if text]

    assert names[:-1] == [f"Mine {n}" for n in reversed(range(2, MAX_OWN + 2))]


def test_with_none_of_their_own_the_included_lead_with_no_separator_above(window, included_base):
    save(included_base, "single", "Single Card", 1)

    assert entries(filled(window.new_reading_menu)) == [
        "Single Card",
        None,
        READINGS["browse_spreads"],
    ]


def test_with_no_spreads_only_browse_is_left(window):
    assert entries(filled(window.new_reading_menu)) == [READINGS["browse_spreads"]]


def test_a_spread_saved_since_the_last_open_shows(window, spreads_base):
    menu = filled(window.new_reading_menu)
    save(spreads_base, "later", "Later", 1)

    assert "Later" in entries(filled(menu))


def test_an_ampersand_in_a_name_is_no_mnemonic(window, spreads_base):
    save(spreads_base, "amp", "Love & Money", 1)

    assert "Love && Money" in entries(filled(window.new_reading_menu))


def test_a_spread_starts_a_staged_reading_of_it(window, spreads_base):
    save(spreads_base, "mine", "Mine", 1)

    entry(filled(window.new_reading_menu), "Mine").trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, ReadingTab)
    assert tab.phase is Phase.STAGED
    assert tab.spread.name == "Mine"


def test_browse_opens_the_librarys_spreads_view(window):
    entry(filled(window.new_reading_menu), READINGS["browse_spreads"]).trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, LibraryTab)
    assert tab.current_view() == LIBRARY_VIEW_SPREADS


def test_file_and_the_plus_menu_hold_it_after_new_spread(window):
    file_menu = window.menuBar().actions()[0].menu()
    submenu = window.new_reading_menu.menuAction()

    for menu in (file_menu, window.new_tab_menu):
        actions = menu.actions()
        assert actions[actions.index(window.new_spread_action) + 1] is submenu
    assert submenu.text() == MAIN_WINDOW["new_reading_from_spread"]


def test_the_welcome_tabs_first_button_is_new_reading_with_the_menu(window, spreads_base):
    save(spreads_base, "mine", "Mine", 1)
    welcome = window.tab_widget.widget(0)
    button = welcome.findChildren(QPushButton)[0]

    assert button.text() == MAIN_WINDOW["welcome_new_reading"]
    assert "Mine" in entries(filled(button.menu()))


# -- the designer -----------------------------------------------------------


def test_the_designer_cannot_start_a_reading_with_no_slots(qtbot):
    tab = SpreadTab()
    qtbot.addWidget(tab)

    assert not tab.start_reading_action.isEnabled()
    tab.add_next_slot()
    assert tab.start_reading_action.isEnabled()
    tab.scene.clearSelection()
    tab.slots()[0].setSelected(True)
    tab.on_delete_card()
    assert not tab.start_reading_action.isEnabled()


def test_the_designer_starts_a_reading_of_its_unsaved_spread(window, qtbot):
    tab = window.new_spread_tab()
    tab.add_next_slot()
    tab.add_next_slot()
    tab.rename("Draft")

    tab.start_reading_action.trigger()

    reading = window.tab_widget.currentWidget()
    assert isinstance(reading, ReadingTab)
    assert reading.phase is Phase.STAGED
    assert reading.spread.name == "Draft"
    assert len(reading.slots()) == 2
    assert tab.has_unsaved_changes()


def test_the_designers_button_says_start_reading(qtbot):
    tab = SpreadTab()
    qtbot.addWidget(tab)

    assert tab.start_reading_action.text() == READINGS["open"]
    assert tab.start_reading_action in tab.toolbar.actions()
