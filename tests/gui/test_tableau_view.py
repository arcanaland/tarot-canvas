import json

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QScrollBar
from pytestqt.qtbot import QtBot

from tarot_canvas.settings import (
    DECK_VIEW_DENSITY_KEY,
    DECK_VIEW_MODE_KEY,
    DECK_VIEW_MODE_SECTIONS,
    DECK_VIEW_MODE_TABLEAU,
    get_settings,
)
from tarot_canvas.ui.card_transfer import CARD_MIME
from tarot_canvas.ui.deck_view import view_text
from tarot_canvas.ui.deck_view.card_model import CardRole, KindRole
from tarot_canvas.ui.deck_view.tableau_model import KIND_GHOST, ROW_LABELS, DimmedRole
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tests.conftest import MINIMAL_DECK_PATH
from tests.gui.test_tableau_model import deck_without


def shown(qtbot, deck_path, width=1300, height=800, mode=DECK_VIEW_MODE_TABLEAU, density=None):
    get_settings().setValue(DECK_VIEW_MODE_KEY, mode)
    if density:
        get_settings().setValue(DECK_VIEW_DENSITY_KEY, density)
    widget = DeckViewTab(str(deck_path))
    qtbot.addWidget(widget)
    widget.resize(width, height)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def tab(qtbot, full_deck):
    return shown(qtbot, full_deck.deck_path)


def at(tab, row, column):
    return tab.tableau_model.index(row, column)


def card_id(index):
    card = index.data(CardRole)
    return card["id"] if card else None


def press(view, key, modifier=Qt.KeyboardModifier.NoModifier):
    QtBot.keyClick(view, key, modifier)


def labels(tab):
    model = tab.tableau_model
    return [model.row_kind(row) for row in range(model.rowCount())].index(ROW_LABELS)


def horizontal_bar(tab):
    return tab.scroll.horizontalScrollBar()


# -- the view ---------------------------------------------------------------------


def test_every_card_cell_is_a_card_wide_and_tall(tab):
    rects = [tab.tableau.visualRect(at(tab, *cell)) for cell in tab.tableau_model.card_cells()]
    width = units.cover_size(units.DENSITY_MEDIUM)[0] + 2 * units.LARGE_SPACING

    assert {rect.width() for rect in rects} == {width}
    assert len({rect.height() for rect in rects}) == 1


def test_labels_never_take_the_selection(tab):
    tab.tableau.selectAll()
    selected = {(i.row(), i.column()) for i in tab.tableau.selectionModel().selectedIndexes()}

    assert selected == set(tab.tableau_model.card_cells())


def test_the_tableau_fits_its_contents_and_never_scrolls_itself(tab):
    tableau = tab.tableau
    assert tableau.width() == tableau.horizontalHeader().length()
    assert tableau.height() == tableau.verticalHeader().length()
    assert tableau.verticalScrollBar().maximum() == 0
    assert tableau.horizontalScrollBar().maximum() == 0


def test_a_density_change_resizes_the_tableau(tab):
    before = tab.tableau.width()
    tab.zoom("in")

    assert tab.tableau.width() > before
    assert tab.tableau.width() == tab.tableau.horizontalHeader().length()


# -- the keyboard -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "key", "end"),
    [
        ("major_arcana.07", Qt.Key.Key_Right, "major_arcana.07"),
        ("major_arcana.00", Qt.Key.Key_Down, "major_arcana.04"),
        ("major_arcana.18", Qt.Key.Key_Down, "minor_arcana.cups.ace"),
        ("minor_arcana.wands.ace", Qt.Key.Key_Left, "minor_arcana.wands.ace"),
        ("minor_arcana.wands.ace", Qt.Key.Key_Up, "major_arcana.17"),
        ("major_arcana.01", Qt.Key.Key_Right, "major_arcana.02"),
        ("major_arcana.01", Qt.Key.Key_End, "minor_arcana.pentacles.king"),
        ("minor_arcana.cups.five", Qt.Key.Key_Home, "major_arcana.00"),
    ],
)
def test_arrows_step_between_cards_only(tab, start, key, end):
    model = tab.tableau_model
    (start_cell,) = (cell for cell in model.card_cells() if card_id(at(tab, *cell)) == start)
    tab.tableau.setCurrentIndex(at(tab, *start_cell))

    press(tab.tableau, key)

    assert card_id(tab.tableau.currentIndex()) == end


def test_arrows_skip_a_ghost(qtbot, tmp_path):
    deck = deck_without(tmp_path, "minor_arcana.cups.ace")
    tab = shown(qtbot, deck.deck_path)
    first = labels(tab) + 1
    assert at(tab, first, 3).data(KindRole) == KIND_GHOST
    tab.tableau.setCurrentIndex(at(tab, first, 2))

    press(tab.tableau, Qt.Key.Key_Right)

    assert card_id(tab.tableau.currentIndex()) == "minor_arcana.swords.ace"


# -- the view bar -----------------------------------------------------------------


def test_the_view_bar_is_two_exclusive_icon_buttons_with_placeholder_names(tab):
    sections = tab.view_buttons[DECK_VIEW_MODE_SECTIONS]
    tableau = tab.view_buttons[DECK_VIEW_MODE_TABLEAU]

    assert tab.view_group.exclusive()
    assert sections.isCheckable() and tableau.isCheckable()
    assert sections.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert sections.toolTip() == view_text.SECTIONS_TOOLTIP
    assert sections.accessibleName() == view_text.SECTIONS_NAME
    assert tableau.toolTip() == view_text.TABLEAU_TOOLTIP
    assert tableau.accessibleName() == view_text.TABLEAU_NAME
    assert sections.parentWidget().accessibleName() == view_text.VIEW_BAR_NAME
    assert tableau.isChecked() and not sections.isChecked()

    sections.click()
    assert sections.isChecked() and not tableau.isChecked()
    assert tab.current_view() is tab.grid


def test_the_choice_persists_and_a_new_tab_opens_in_it(qtbot, full_deck):
    first = shown(qtbot, full_deck.deck_path, mode=DECK_VIEW_MODE_SECTIONS)
    assert first.current_view() is first.grid

    first.view_buttons[DECK_VIEW_MODE_TABLEAU].click()
    assert get_settings().value(DECK_VIEW_MODE_KEY) == DECK_VIEW_MODE_TABLEAU

    second = DeckViewTab(str(full_deck.deck_path))
    qtbot.addWidget(second)
    assert second.current_view() is second.tableau
    assert second.view_buttons[DECK_VIEW_MODE_TABLEAU].isChecked()


def test_an_unknown_stored_mode_falls_back_to_sections(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path, mode="carousel")
    assert tab.mode == DECK_VIEW_MODE_SECTIONS
    assert tab.current_view() is tab.grid


# -- switching --------------------------------------------------------------------


def selected_ids(tab):
    return [card["id"] for card in tab.selected_cards()]


def test_the_selection_and_current_card_cross_both_ways(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path, mode=DECK_VIEW_MODE_SECTIONS)
    model = tab.grid.model()
    rows = [r for r in range(model.rowCount()) if model.index(r, 0).data(CardRole)]
    picks = [model.index(rows[n], 0) for n in (3, 30, 77)]
    selection = tab.grid.selectionModel()
    for index in picks:
        selection.select(index, QItemSelectionModel.SelectionFlag.Select)
    selection.setCurrentIndex(picks[1], QItemSelectionModel.SelectionFlag.NoUpdate)
    wanted = selected_ids(tab)
    assert len(wanted) == 3

    tab.view_buttons[DECK_VIEW_MODE_TABLEAU].click()
    assert tab.current_view() is tab.tableau
    assert selected_ids(tab) == wanted
    assert card_id(tab.tableau.currentIndex()) == card_id(picks[1])

    tab.view_buttons[DECK_VIEW_MODE_SECTIONS].click()
    assert selected_ids(tab) == wanted
    assert card_id(tab.grid.currentIndex()) == card_id(picks[1])


def test_a_card_find_hid_has_no_selection_to_carry_back(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path)
    tab.tableau.setCurrentIndex(at(tab, 0, 3))  # The Fool
    tab.search_field.setText("king")

    tab.view_buttons[DECK_VIEW_MODE_SECTIONS].click()

    assert selected_ids(tab) == []


def test_find_dims_the_tableau_and_leaves_every_slot(tab):
    cells = tab.tableau_model.card_cells()
    tab.search_field.setText("king")

    assert tab.tableau_model.card_cells() == cells
    dimmed = [at(tab, *cell).data(DimmedRole) for cell in cells]
    assert dimmed.count(False) == 4


def test_edit_copy_in_the_tableau_copies_its_selection(tab, clipboard):
    selection = tab.tableau.selectionModel()
    for cell in [(0, 3), (1, 0)]:
        selection.select(at(tab, *cell), QItemSelectionModel.SelectionFlag.Select)

    assert tab.can_copy_card()
    tab.copy_card()

    payload = json.loads(bytes(clipboard.mimeData().data(CARD_MIME)).decode())
    assert payload["card_ids"] == ["major_arcana.00", "major_arcana.01"]


def test_activating_a_tableau_card_opens_it(tab, qtbot):
    tab.tableau.setCurrentIndex(at(tab, 1, 0))
    with qtbot.waitSignal(tab.card_action_requested, timeout=1000) as opened:
        press(tab.tableau, Qt.Key.Key_Return)
    assert opened.args[1]["id"] == "major_arcana.01"


# -- a new canvas -----------------------------------------------------------------


def test_new_canvas_from_selection_sends_the_selected_cards_in_deck_order(tab, qtbot):
    selection = tab.tableau.selectionModel()
    for cell in [(1, 0), (0, 3)]:
        selection.select(at(tab, *cell), QItemSelectionModel.SelectionFlag.Select)
    actions = {a.text(): a for a in tab.card_menu(at(tab, 0, 3)).actions()}

    with qtbot.waitSignal(tab.new_canvas_requested, timeout=1000) as requested:
        actions["Create New Canvas From Selection"].trigger()

    cards, deck = requested.args
    assert [card["id"] for card in cards] == ["major_arcana.00", "major_arcana.01"]
    assert deck is tab.deck


# -- centring ---------------------------------------------------------------------


def test_a_wide_tab_centres_the_tableau_with_no_horizontal_bar(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path, width=1300, density=units.DENSITY_SMALL)
    # The area hides its bars after a deferred relayout
    qtbot.waitUntil(lambda: not horizontal_bar(tab).isVisible())
    viewport = tab.scroll.viewport()
    left = tab.tableau.mapTo(viewport, tab.tableau.rect().topLeft()).x()
    right = viewport.width() - (left + tab.tableau.width())

    assert abs(left - right) <= 1
    assert horizontal_bar(tab).maximum() == 0


def test_a_narrow_tab_scrolls_the_tableau_sideways_and_sections_do_not(qtbot, full_deck):
    tab = shown(qtbot, full_deck.deck_path, width=1000, density=units.DENSITY_LARGE)
    qtbot.waitUntil(lambda: horizontal_bar(tab).isVisible())

    tab.view_buttons[DECK_VIEW_MODE_SECTIONS].click()
    qtbot.waitUntil(lambda: not horizontal_bar(tab).isVisible())
    assert all(
        not bar.isVisible()
        for bar in tab.findChildren(QScrollBar)
        if bar.orientation() == Qt.Orientation.Horizontal
    )


def test_the_minimal_deck_shows_ghosts(qtbot):
    tab = shown(qtbot, MINIMAL_DECK_PATH)
    model = tab.tableau_model
    ghosts = [
        (row, column)
        for row in range(model.rowCount())
        for column in range(model.columnCount())
        if at(tab, row, column).data(KindRole) == KIND_GHOST
    ]
    # Every minor is excluded, so there is no minor block
    assert len(ghosts) == 20
    tab.tableau.viewport().grab()
