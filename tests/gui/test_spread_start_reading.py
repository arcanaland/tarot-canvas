"""A spread row's ▶, its pane's split button and its menu start a reading with a chosen deck."""

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent, QIcon
from PyQt6.QtWidgets import QMenu, QStyleOptionViewItem, QToolButton, QToolTip

from tarot_canvas.models import spreads
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.spreads import BUNDLED_SPREADS_PATH
from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_SPREADS,
    get_readings_deck,
    set_readings_deck,
)
from tarot_canvas.ui import units
from tarot_canvas.ui.commands import key_text, tooltip_with_keys
from tarot_canvas.ui.library.row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.section_row import is_section
from tarot_canvas.ui.library.spreads.model import SpreadPathRole
from tarot_canvas.ui.library.spreads.row_delegate import SpreadRowDelegate
from tarot_canvas.ui.library.tab import LibraryTab
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import READINGS, SPREADS
from tarot_canvas.ui.tabs.reading_tab import ReadingTab
from tests.conftest import write_full_deck
from tests.gui.test_note_row_delegate import ROW_WIDTH, make_option
from tests.gui.test_spreads_view import index_of, menu_action, menu_entries


@pytest.fixture
def decks(tmp_path, stub_deck_manager, qapp):
    """Two installed decks, the first the reference"""
    first = TarotDeck(str(write_full_deck(tmp_path / "first", name="First")))
    second = TarotDeck(str(write_full_deck(tmp_path / "second", name="Second")))
    stub_deck_manager.get_reference_deck = lambda: first
    stub_deck_manager.get_all_decks = lambda: [first, second]
    return first, second


@pytest.fixture
def library(qtbot, monkeypatch, spreads_base, decks):
    """The Spreads view of a shown window's Library, listing the spreads that ship"""
    monkeypatch.setattr(spreads, "included_base", lambda: BUNDLED_SPREADS_PATH)
    window = MainWindow()
    qtbot.addWidget(window)
    library = LibraryTab()
    window.tab_widget.addTab(library, "Library")
    window.tab_widget.setCurrentWidget(library)
    library.show_view(LIBRARY_VIEW_SPREADS)
    window.resize(1200, 800)
    with qtbot.waitExposed(window):
        window.show()
    return library


def page_of(library):
    return library.spreads_page


def row_option(page, index):
    option = QStyleOptionViewItem()
    option.initFrom(page.list_view)
    option.rect = page.list_view.visualRect(index)
    return option


def row_layout(page, name):
    return page.row_delegate._layout(row_option(page, index_of(page, name)))


def current_tab(library):
    return library.window().tab_widget.currentWidget()


def deck_entries(menu):
    return [(action.text(), action.isChecked()) for action in menu.actions()]


# -- the row's buttons


def test_a_spread_row_has_play_then_menu_at_its_trailing_end(qapp):
    delegate = SpreadRowDelegate()
    # Its sizeHint asks the index whether it is a heading, so a note row's option stands in
    layout = delegate._layout(make_option(qapp, NoteRowDelegate()))

    play, menu = layout.buttons
    assert menu == layout.menu
    assert menu.right() == ROW_WIDTH - 1 - units.LARGE_SPACING
    assert play.right() < menu.left()
    assert play.center().y() == menu.center().y()
    for rect in (layout.title, layout.subtitle, layout.preview):
        assert rect.right() < play.left()


def test_a_spread_row_paints_play_then_menu_and_a_heading_paints_neither(
    library, qtbot, monkeypatch
):
    page = page_of(library)
    painted = []
    from_theme = QIcon.fromTheme

    def record(name, *args):
        painted.append(name)
        return from_theme(name, *args)

    monkeypatch.setattr(QIcon, "fromTheme", record)
    model = page.list_model
    rows = [model.index(row, 0) for row in range(model.rowCount())]
    assert any(is_section(index) for index in rows)

    page.list_view.viewport().grab()  # paints every row, the heading too

    spread_rows = sum(1 for index in rows if not is_section(index))
    assert painted == ["media-playback-start", "overflow-menu"] * spread_rows


def test_each_button_has_its_tooltip(library, monkeypatch):
    page = page_of(library)
    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda _pos, text, *_: shown.append(text))
    index = index_of(page, "Celtic Cross")
    option = row_option(page, index)
    play, menu = page.row_delegate._layout(option).buttons

    for rect in (play, menu):
        event = QHelpEvent(QEvent.Type.ToolTip, rect.center(), QPoint(0, 0))
        assert page.row_delegate.helpEvent(event, page.list_view, option, index)

    assert shown == [
        tooltip_with_keys(READINGS["open"], "library.start_reading"),
        SPREADS["menu_tooltip"],
    ]
    assert key_text("library.start_reading") in shown[0]


def test_a_hover_sweep_over_every_row_raises_nothing(library, qtbot, monkeypatch):
    """pytest-qt fails the test on an exception raised inside a Qt virtual"""
    monkeypatch.setattr(QToolTip, "showText", lambda *_: None)
    page = page_of(library)
    view = page.list_view
    for row in range(page.list_model.rowCount()):
        index = page.list_model.index(row, 0)
        option = row_option(page, index)
        rect = option.rect
        for x in range(rect.left(), rect.right() + 1, 2):
            pos = QPoint(x, rect.center().y())
            qtbot.mouseMove(view.viewport(), pos)
            event = QHelpEvent(QEvent.Type.ToolTip, pos, view.viewport().mapToGlobal(pos))
            page.row_delegate.helpEvent(event, view, option, index)


def test_clicking_play_starts_a_reading_with_the_remembered_deck_and_leaves_the_pane(
    library, qtbot, decks
):
    _first, second = decks
    set_readings_deck(second.deck_path)
    page = page_of(library)
    assert not library.details_pane_is_open()

    qtbot.mouseClick(
        page.list_view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=row_layout(page, "Celtic Cross").buttons[0].center(),
    )

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 10
    assert tab.deck is second
    assert not library.details_pane_is_open()


def test_a_play_click_does_not_swallow_the_next_row_click(library, qtbot):
    page = page_of(library)
    viewport = page.list_view.viewport()
    qtbot.mouseClick(
        viewport,
        Qt.MouseButton.LeftButton,
        pos=row_layout(page, "Basic Three-Card Spread").buttons[0].center(),
    )
    library.window().tab_widget.setCurrentWidget(library)

    centre = page.list_view.visualRect(index_of(page, "Celtic Cross")).center()
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=centre)

    assert library.details_pane_is_open()


# -- the pane's split button


def show_pane_for(library, qtbot, name):
    page = page_of(library)
    centre = page.list_view.visualRect(index_of(page, name)).center()
    qtbot.mouseClick(page.list_view.viewport(), Qt.MouseButton.LeftButton, pos=centre)
    assert library.details_pane_is_open()
    return page.details_pane


def test_the_panes_split_button_sits_before_edit(library, qtbot):
    pane = show_pane_for(library, qtbot, "Celtic Cross")
    button = pane.reading_button

    assert button.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
    assert button.text() == READINGS["open"]
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert button.autoRaise()
    assert button.geometry().right() < pane.edit_button.geometry().left()


def test_the_split_buttons_main_part_starts_with_the_remembered_deck(library, qtbot, decks):
    first, _second = decks
    pane = show_pane_for(library, qtbot, "Celtic Cross")

    pane.reading_button.click()

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 10
    assert tab.deck is first


def test_the_arrow_lists_every_deck_with_the_remembered_one_checked(library, qtbot, decks):
    pane = show_pane_for(library, qtbot, "Celtic Cross")
    menu = pane.reading_button.menu()
    menu.aboutToShow.emit()

    assert deck_entries(menu) == [("First", True), ("Second", False)]


def test_choosing_another_deck_starts_with_it_and_remembers_it(library, qtbot, decks):
    _first, second = decks
    pane = show_pane_for(library, qtbot, "Celtic Cross")
    menu = pane.reading_button.menu()
    menu.aboutToShow.emit()

    menu_action(menu, "Second").trigger()

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert tab.deck is second
    assert get_readings_deck() == second.deck_path
    menu.aboutToShow.emit()
    assert deck_entries(menu) == [("First", False), ("Second", True)]


def test_the_deck_list_is_rebuilt_as_it_opens(library, qtbot, decks, stub_deck_manager, tmp_path):
    pane = show_pane_for(library, qtbot, "Celtic Cross")
    third = TarotDeck(str(write_full_deck(tmp_path / "third", name="Third & Co")))
    stub_deck_manager.get_all_decks = lambda: [*decks, third]

    pane.reading_button.menu().aboutToShow.emit()

    assert [action.text() for action in pane.reading_button.menu().actions()] == [
        "First",
        "Second",
        "Third && Co",
    ]


# -- the menu


def test_the_menus_submenu_holds_the_same_decks_as_the_arrow(library, qtbot, decks):
    _first, second = decks
    set_readings_deck(second.deck_path)
    page = page_of(library)
    pane = show_pane_for(library, qtbot, "Celtic Cross")
    arrow = pane.reading_button.menu()
    arrow.aboutToShow.emit()

    menu = page.row_menu(index_of(page, "Celtic Cross"))
    submenu = menu_action(menu, READINGS["open_with"]).menu()

    assert menu_entries(menu)[:2] == [READINGS["open"], READINGS["open_with"]]
    assert deck_entries(submenu) == deck_entries(arrow) == [("First", False), ("Second", True)]


def test_the_submenus_deck_starts_a_reading_with_it(library, decks, monkeypatch):
    first, second = decks
    set_readings_deck(second.deck_path)
    monkeypatch.setattr(QMenu, "exec", lambda *_: None)
    page = page_of(library)
    menu = page.row_menu(index_of(page, "Basic Three-Card Spread"))

    menu_action(menu_action(menu, READINGS["open_with"]).menu(), "First").trigger()

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 3
    assert tab.deck is first
    assert get_readings_deck() == first.deck_path


# -- the key


CTRL = Qt.KeyboardModifier.ControlModifier


def select(library, name):
    page = page_of(library)
    page.select(index_of(page, name).data(SpreadPathRole))
    return page


def test_ctrl_return_starts_a_reading_from_the_selected_spread(library, qtbot, decks):
    first, _second = decks
    page = select(library, "Celtic Cross")
    page.list_view.setFocus()

    qtbot.keyClick(page.list_view, Qt.Key.Key_Return, CTRL)

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 10
    assert tab.deck is first


def test_ctrl_return_works_from_the_search_field(library, qtbot):
    select(library, "Celtic Cross")
    library.search_field.setFocus()

    qtbot.keyClick(library.search_field, Qt.Key.Key_Return, CTRL)

    assert isinstance(current_tab(library), ReadingTab)


def test_ctrl_return_with_nothing_selected_or_in_another_view_does_nothing(library, qtbot):
    tabs = library.window().tab_widget
    count = tabs.count()
    page = page_of(library)
    page.list_view.setFocus()
    qtbot.keyClick(page.list_view, Qt.Key.Key_Return, CTRL)
    assert tabs.count() == count

    select(library, "Celtic Cross")
    library.show_view(LIBRARY_VIEW_DECKS)
    library.search_field.setFocus()
    qtbot.keyClick(library.search_field, Qt.Key.Key_Return, CTRL)
    assert tabs.count() == count


def test_the_menu_and_the_split_button_name_the_key(library, qtbot):
    key = key_text("library.start_reading")
    assert key
    page = page_of(library)
    menu = page.row_menu(index_of(page, "Celtic Cross"))
    pane = show_pane_for(library, qtbot, "Celtic Cross")

    assert menu.actions()[0].text() == f"{READINGS['open']}\t{key}"
    assert key in pane.reading_button.toolTip()


# -- from the search field to a reading, by keyboard alone


@pytest.mark.parametrize("key", [Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_a_key_in_the_search_field_selects_the_first_match(library, qtbot, key):
    page = page_of(library)
    library.find()
    qtbot.keyClicks(library.search_field, "Cross")
    assert page._selected_path() is None  # the search dropped any selection

    qtbot.keyClick(library.search_field, key)

    assert page.list_view.hasFocus()
    assert page.list_view.currentIndex().data() == "Celtic Cross"
    assert page._selected_path() is not None
    assert library.search_field.text() == "Cross"


def test_the_first_match_skips_a_heading(library, qtbot):
    page = page_of(library)
    assert is_section(page.list_model.index(0, 0))
    library.search_field.setFocus()

    qtbot.keyClick(library.search_field, Qt.Key.Key_Down)

    assert not is_section(page.list_view.currentIndex())


def test_find_cross_then_ctrl_return_starts_the_reading(library, qtbot):
    library.find()
    qtbot.keyClicks(library.search_field, "Cross")
    qtbot.keyClick(library.search_field, Qt.Key.Key_Down)

    qtbot.keyClick(page_of(library).list_view, Qt.Key.Key_Return, CTRL)

    tab = current_tab(library)
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 10


def test_a_key_with_no_match_stays_in_the_field(library, qtbot):
    library.find()
    qtbot.keyClicks(library.search_field, "no such spread")

    qtbot.keyClick(library.search_field, Qt.Key.Key_Return)

    assert library.search_field.hasFocus()


def test_the_deck_grid_takes_the_same_keys(library, qtbot):
    library.show_view(LIBRARY_VIEW_DECKS)
    library.search_field.setFocus()

    qtbot.keyClick(library.search_field, Qt.Key.Key_Down)

    assert library.decks_page.list_view.hasFocus()
    assert library.decks_page.list_view.selectionModel().isSelected(
        library.decks_page.list_view.currentIndex()
    )
