"""Pinned decks lead the grid, and hidden ones wait behind its quiet cell"""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel, QPoint, Qt
from PyQt6.QtWidgets import QProxyStyle, QStyle

from tarot_canvas.models import library_curation as curation
from tarot_canvas.settings import record_deck_opened
from tarot_canvas.ui.library.decks.model import (
    SORT_AUTHOR,
    SORT_RECENT,
    DeckFilterProxyModel,
    DeckHiddenRole,
    DeckListModel,
    DeckRole,
    EntryRole,
)
from tarot_canvas.ui.library.decks.page import DecksPage
from tarot_canvas.ui.library.roles import SORT_COUNT, SORT_NAME, DimmedRole, PinnedRole, ToggleRole
from tarot_canvas.ui.strings import LIBRARY, SPREADS
from tests.unit.test_library_model import catalog_entry, fake_deck

NAMES = ["Aurora", "Birch", "Cedar", "Dune"]
SORTS = [SORT_NAME, SORT_AUTHOR, SORT_COUNT, SORT_RECENT]
SHOW_ONE = SPREADS["hidden_show"].format(count=1)
COLLAPSE = SPREADS["hidden_collapse"]


def identifier(name):
    return f"x/deck/{name.lower()}"


def deck(name, **fields):
    fields.setdefault("identifier", identifier(name))
    return fake_deck(name, **fields)


def hide(*names):
    for name in names:
        curation.set_deck_hidden(identifier(name), True)


def pin(*names):
    for name in names:
        curation.set_deck_pinned(identifier(name), True)


@pytest.fixture
def decks():
    return [deck(name) for name in NAMES]


@pytest.fixture
def entries():
    return []


@pytest.fixture
def page(qtbot, monkeypatch, decks, entries):
    library = SimpleNamespace(decks=lambda: list(decks), rescan=lambda: None)
    catalog = SimpleNamespace(entries=lambda: entries, cover_path=lambda entry: None)
    catalog.entries_changed = catalog.cover_ready = SimpleNamespace(connect=lambda slot: None)
    catalog.activate = lambda: None
    monkeypatch.setattr("tarot_canvas.ui.library.decks.page.deck_library", library)
    monkeypatch.setattr("tarot_canvas.ui.library.decks.page.deck_catalog", lambda: catalog)
    monkeypatch.setattr("tarot_canvas.ui.library.decks.model.deck_catalog", lambda: catalog)
    page = DecksPage()
    qtbot.addWidget(page)
    page.set_sort_key(SORT_NAME)
    return page


@pytest.fixture(autouse=True)
def pointer(monkeypatch):
    """Where the mouse is, which QTest's clicks don't move"""
    at = SimpleNamespace(point=QPoint(-10000, -10000))
    cursor = SimpleNamespace(pos=lambda: at.point)
    monkeypatch.setattr("tarot_canvas.ui.library.list_page.QCursor", cursor)
    return at


@pytest.fixture
def shown_page(page, qtbot):
    page.resize(1100, 700)
    with qtbot.waitActive(page):
        page.show()
        page.activateWindow()
    page.list_view.setFocus()
    return page


def rows(model):
    return [model.index(row, 0) for row in range(model.rowCount())]


def names(page):
    return [index.data() for index in rows(page.list_model)]


def cover(page, name):
    return next(index for index in rows(page.list_model) if index.data() == name)


def toggle(page):
    return next(index for index in rows(page.list_model) if index.data(ToggleRole))


def trigger(page, name, text):
    menu = page.row_menu(cover(page, name))
    next(action for action in menu.actions() if action.text() == text).trigger()


def click(page, qtbot, pointer, index, button=Qt.MouseButton.LeftButton):
    view = page.list_view
    view.scrollTo(index)
    pos = view.visualRect(index).center()
    pointer.point = view.viewport().mapToGlobal(pos)
    qtbot.mouseClick(view.viewport(), button, pos=pos)


def select(page, name):
    page.list_view.selectionModel().setCurrentIndex(
        cover(page, name), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def selected(page):
    return [index.data() for index in page.list_view.selectedIndexes()]


# -- the order ----------------------------------------------------------------


@pytest.mark.parametrize("key", SORTS)
def test_the_buckets_keep_their_order_under_every_sort(qapp, key):
    decks = [
        deck("Aurora", author="A", majors=1),
        deck("Birch", author="B", majors=2),
        deck("Cedar", author="C", majors=3),
        deck("Dune", author="D", majors=4),
        deck("Elm", author="E", majors=5),
        deck("Fen", author="F", majors=6),
    ]
    for when, name in enumerate(["Dune", "Elm", "Cedar", "Birch", "Aurora"], start=1):
        record_deck_opened(f"/decks/{name}", when=when)
    pin("Dune", "Elm")
    hide("Fen")
    model = DeckListModel(decks, entries=[catalog_entry("aquatic-tarot")])
    proxy = DeckFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_sort_key(key)

    pinned = ["Elm", "Dune"] if key == SORT_RECENT else ["Dune", "Elm"]
    installed = ["Aurora", "Birch", "Cedar"]
    assert [index.data() for index in rows(proxy)] == [
        *pinned,
        *installed,
        SHOW_ONE,
        "Aquatic Tarot",
    ]


def test_a_download_repaints_its_ghost_below_the_toggle(qapp, decks):
    hide("Birch")
    entry = catalog_entry("aquatic-tarot")
    model = DeckListModel(decks, entries=[entry])
    changed = []
    model.dataChanged.connect(lambda top, bottom, *_: changed.append(top.row()))

    model.download_changed(entry.slug)

    assert [model.index(row, 0).data(EntryRole) for row in changed] == [entry]


def test_a_pin_in_a_hand_edit_wins_over_its_hide(qapp, decks, curation_file):
    key = identifier("Birch")
    curation_file.write_text(f'[decks]\npinned = ["{key}"]\nhidden = ["{key}"]\n')
    model = DeckListModel(decks)

    assert model.index(1, 0).data(PinnedRole)
    assert not model.index(1, 0).data(DeckHiddenRole)
    assert model.rowCount() == len(decks)


# -- the menu -----------------------------------------------------------------


def test_pin_leads_the_grid_and_flips_to_unpin(page):
    trigger(page, "Cedar", SPREADS["pin"])
    assert names(page) == ["Cedar", "Aurora", "Birch", "Dune"]

    trigger(page, "Cedar", SPREADS["unpin"])
    assert names(page) == NAMES


def test_hide_leaves_the_grid_and_flips_to_unhide(page):
    trigger(page, "Birch", LIBRARY["hide_deck"])
    assert names(page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]

    page.toggle_hidden()
    trigger(page, "Birch", LIBRARY["unhide_deck"])
    assert names(page) == NAMES


def test_pinning_a_hidden_deck_that_shows_unhides_it(page):
    hide("Birch")
    page.toggle_hidden()

    trigger(page, "Birch", SPREADS["pin"])

    assert names(page)[0] == "Birch"
    assert not cover(page, "Birch").data(DimmedRole)


def test_the_toggle_has_no_menu_and_no_details(page):
    hide("Birch")

    assert page.row_menu(toggle(page)) is None
    assert page._details_for(toggle(page)) is None


# -- the cell -----------------------------------------------------------------


def test_a_click_shows_the_hidden_dimmed_and_another_puts_them_away(shown_page, qtbot, pointer):
    hide("Birch")

    click(shown_page, qtbot, pointer, toggle(shown_page))
    assert names(shown_page) == [*NAMES, COLLAPSE]
    assert cover(shown_page, "Birch").data(DimmedRole)

    click(shown_page, qtbot, pointer, toggle(shown_page))
    assert names(shown_page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]


class SingleClickStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ItemView_ActivateItemOnSingleClick:
            return 1
        return super().styleHint(hint, option, widget, returnData)


@pytest.fixture
def single_click_page(shown_page):
    style = SingleClickStyle()
    style.setParent(shown_page)
    shown_page.list_view.setStyle(style)
    return shown_page


def test_a_click_that_also_activates_toggles_once(single_click_page, qtbot, pointer):
    page = single_click_page
    hide("Birch")

    click(page, qtbot, pointer, toggle(page))
    assert names(page) == [*NAMES, COLLAPSE]

    click(page, qtbot, pointer, toggle(page))
    assert names(page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]


@pytest.mark.parametrize("button", [Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton])
def test_only_a_left_click_toggles(single_click_page, qtbot, pointer, button):
    hide("Birch")

    click(single_click_page, qtbot, pointer, toggle(single_click_page), button)

    assert names(single_click_page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]


def test_a_double_click_toggles_once(shown_page, qtbot, pointer):
    hide("Birch")
    view = shown_page.list_view
    pos = view.visualRect(toggle(shown_page)).center()
    pointer.point = view.viewport().mapToGlobal(pos)

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)

    assert names(shown_page) == [*NAMES, COLLAPSE]


def test_return_toggles_both_ways_without_selecting_the_cell(shown_page, qtbot):
    hide("Birch")
    select(shown_page, "Dune")

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Right)
    assert shown_page.list_view.currentIndex() == toggle(shown_page)
    assert selected(shown_page) == []
    assert shown_page.details_pane.details().deck.metadata.name == "Dune"

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Return)
    assert names(shown_page) == [*NAMES, COLLAPSE]
    assert shown_page.list_view.currentIndex() == toggle(shown_page)
    assert selected(shown_page) == []

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Return)
    assert names(shown_page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]


def test_showing_is_kept_through_a_refresh_and_not_by_a_new_page(page, decks):
    hide("Birch")
    page.toggle_hidden()

    page.refresh()

    assert names(page) == [*NAMES, COLLAPSE]
    assert not DeckListModel(decks).shows_hidden()


def test_with_every_deck_hidden_the_cell_remains(page):
    hide(*NAMES)

    assert names(page) == [SPREADS["hidden_show"].format(count=4)]
    assert not page.empty_label.isVisibleTo(page)


# -- search -------------------------------------------------------------------


def test_a_search_finds_a_hidden_deck_dimmed_without_the_cell(page):
    hide("Birch")

    page.set_search("bir")
    assert names(page) == ["Birch"]
    assert cover(page, "Birch").data(DimmedRole)

    page.set_search("")
    assert names(page) == ["Aurora", "Cedar", "Dune", SHOW_ONE]


def test_a_search_that_finds_nothing_says_so_though_decks_are_hidden(page):
    hide("Birch")

    page.set_search("nothing")

    assert names(page) == []
    assert page.empty_label.text() == LIBRARY["empty_no_match"]


# -- the selection ------------------------------------------------------------


@pytest.mark.parametrize(
    ("hidden", "already", "next_cover"),
    [
        ("Aurora", (), "Birch"),
        ("Birch", (), "Cedar"),
        ("Birch", ("Cedar",), "Dune"),
        ("Cedar", ("Aurora",), "Dune"),
        ("Dune", (), "Cedar"),
        ("Dune", ("Aurora",), "Cedar"),
    ],
)
def test_hiding_the_selected_deck_selects_the_next_cover(page, hidden, already, next_cover):
    hide(*already)
    select(page, hidden)

    trigger(page, hidden, LIBRARY["hide_deck"])

    assert selected(page) == [next_cover]
    assert page.details_pane.details().deck.metadata.name == next_cover


@pytest.mark.parametrize("entries", [[catalog_entry("aquatic-tarot")]])
def test_hiding_the_last_deck_steps_over_the_cell_to_the_ghost(page):
    select(page, "Dune")

    trigger(page, "Dune", LIBRARY["hide_deck"])

    assert selected(page) == ["Aquatic Tarot"]


@pytest.mark.parametrize(
    "decks",
    [[deck("Aurora"), deck("Birch", identifier=identifier("Cedar")), deck("Cedar"), deck("Dune")]],
)
def test_decks_sharing_an_identifier_hide_together_and_select_the_next(page):
    select(page, "Cedar")

    trigger(page, "Cedar", LIBRARY["hide_deck"])

    assert names(page) == ["Aurora", "Dune", SPREADS["hidden_show"].format(count=2)]
    assert selected(page) == ["Dune"]


def test_hiding_another_deck_keeps_the_selection(page):
    select(page, "Dune")

    trigger(page, "Birch", LIBRARY["hide_deck"])

    assert selected(page) == ["Dune"]


def test_hiding_does_not_open_the_pane(shown_page):
    select(shown_page, "Birch")
    chosen = []
    shown_page.row_chosen.connect(lambda: chosen.append(True))

    trigger(shown_page, "Birch", LIBRARY["hide_deck"])

    assert chosen == []


def test_pin_and_unhide_keep_the_selection(page):
    hide("Birch")
    page.toggle_hidden()
    select(page, "Birch")

    trigger(page, "Birch", LIBRARY["unhide_deck"])
    assert selected(page) == ["Birch"]

    trigger(page, "Birch", SPREADS["pin"])
    assert selected(page) == ["Birch"]
    assert page.list_view.currentIndex().data(DeckRole).metadata.name == "Birch"
