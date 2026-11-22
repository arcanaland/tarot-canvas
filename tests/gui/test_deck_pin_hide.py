"""The grid's shelves: Pinned leads, and Hidden folds away at the end"""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QProxyStyle, QStyle

from tarot_canvas.models import library_curation as curation
from tarot_canvas.settings import record_deck_opened
from tarot_canvas.ui.library.decks.model import (
    PINNED_SHELF,
    SORT_AUTHOR,
    SORT_RECENT,
    DeckFilterProxyModel,
    DeckListModel,
    DeckRole,
    EntryRole,
    ExpandedRole,
    ShelfRole,
)
from tarot_canvas.ui.library.decks.page import DecksPage
from tarot_canvas.ui.library.roles import SORT_COUNT, SORT_NAME, SectionRole
from tarot_canvas.ui.strings import LIBRARY, SPREADS
from tests.unit.test_library_model import catalog_entry, fake_deck

NAMES = ["Aurora", "Birch", "Cedar", "Dune"]
SORTS = [SORT_NAME, SORT_AUTHOR, SORT_COUNT, SORT_RECENT]
PINNED = SPREADS["section_pinned"]
DECKS = LIBRARY["decks_view"]
AVAILABLE = LIBRARY["shelf_available"]
HIDDEN_ONE = LIBRARY["shelf_hidden"].format(count=1)
GHOST = "Aquatic Tarot"
FOLDED = ["Aurora", "Cedar", "Dune", HIDDEN_ONE]
OPENED = [*FOLDED, "Birch"]


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


def heading(page, text=HIDDEN_ONE):
    return next(
        index for index in rows(page.list_model) if index.data(SectionRole) and index.data() == text
    )


def trigger(page, name, text):
    menu = page.row_menu(cover(page, name))
    next(action for action in menu.actions() if action.text() == text).trigger()


def click(page, qtbot, index, button=Qt.MouseButton.LeftButton):
    view = page.list_view
    view.scrollTo(index)
    pos = view.visualRect(index).center()
    qtbot.mouseClick(view.viewport(), button, pos=pos)


def select(page, name):
    page.list_view.selectionModel().setCurrentIndex(
        cover(page, name), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def selected(page):
    return [index.data() for index in page.list_view.selectedIndexes()]


# -- the order ----------------------------------------------------------------


@pytest.mark.parametrize("key", SORTS)
def test_the_shelves_keep_their_order_and_headings_under_every_sort(qapp, key):
    decks = [
        deck("Aurora", author="A", majors=1),
        deck("Birch", author="B", majors=2),
        deck("Cedar", author="C", majors=3),
        deck("Dune", author="D", majors=4),
        deck("Elm", author="E", majors=5),
        deck("Fen", author="F", majors=6),
        deck("Gorse", author="G", majors=7),
    ]
    for when, name in enumerate(["Gorse", "Fen", "Dune", "Elm", "Cedar", "Birch", "Aurora"], 1):
        record_deck_opened(f"/decks/{name}", when=when)
    pin("Dune", "Elm")
    hide("Fen", "Gorse")
    model = DeckListModel(decks, entries=[catalog_entry("aquatic-tarot")])
    proxy = DeckFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_sort_key(key)
    proxy.toggle_hidden()

    recent = key == SORT_RECENT
    assert [index.data() for index in rows(proxy)] == [
        PINNED,
        *(["Elm", "Dune"] if recent else ["Dune", "Elm"]),
        DECKS,
        "Aurora",
        "Birch",
        "Cedar",
        AVAILABLE,
        GHOST,
        LIBRARY["shelf_hidden"].format(count=2),
        "Fen",
        "Gorse",
    ]


def test_without_a_pin_the_covers_have_no_heading(page):
    assert names(page) == NAMES


def test_with_every_deck_pinned_there_is_no_decks_heading(page):
    pin(*NAMES)

    assert names(page) == [PINNED, *NAMES]


def test_a_download_repaints_its_ghost_and_no_heading(qapp, decks):
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

    assert model.index(1, 0).data(ShelfRole) == PINNED_SHELF
    assert HIDDEN_ONE not in [index.data() for index in rows(model)]


# -- the menu -----------------------------------------------------------------


def test_pin_leads_the_grid_and_flips_to_unpin(page):
    trigger(page, "Cedar", SPREADS["pin"])
    assert names(page) == [PINNED, "Cedar", DECKS, "Aurora", "Birch", "Dune"]

    trigger(page, "Cedar", SPREADS["unpin"])
    assert names(page) == NAMES


def test_hide_puts_a_deck_under_hidden_and_flips_to_unhide(page):
    trigger(page, "Birch", LIBRARY["hide_deck"])
    assert names(page) == FOLDED

    page.toggle_hidden()
    trigger(page, "Birch", LIBRARY["unhide_deck"])
    assert names(page) == NAMES


def test_pinning_a_hidden_deck_that_shows_unhides_it(page):
    hide("Birch")
    page.toggle_hidden()

    trigger(page, "Birch", SPREADS["pin"])

    assert names(page) == [PINNED, "Birch", DECKS, "Aurora", "Cedar", "Dune"]


def test_a_heading_has_no_menu_and_no_details(page):
    hide("Birch")

    assert page.row_menu(heading(page)) is None
    assert page._details_for(heading(page)) is None


# -- the headings -------------------------------------------------------------


@pytest.mark.parametrize("width", [560, 1100])
@pytest.mark.parametrize("entries", [[catalog_entry("aquatic-tarot")]])
def test_a_heading_has_its_own_line_as_wide_as_the_view(shown_page, qtbot, width):
    pin("Cedar")
    hide("Birch")
    shown_page.resize(width, 700)
    view = shown_page.list_view

    def fits():
        line = view.viewport().width() - 2 * view.spacing()
        every = rows(shown_page.list_model)
        rects = [view.rectForIndex(index) for index in every]
        for at, index in enumerate(every):
            if not index.data(SectionRole):
                continue
            assert rects[at].width() == line
            assert all(rect.bottom() < rects[at].top() for rect in rects[:at])
            assert all(rect.top() > rects[at].bottom() for rect in rects[at + 1 :])

    qtbot.waitUntil(fits)


def test_a_click_opens_hidden_and_another_folds_it(shown_page, qtbot):
    hide("Birch")
    assert heading(shown_page).data(ExpandedRole) is False

    click(shown_page, qtbot, heading(shown_page))
    assert names(shown_page) == OPENED
    assert heading(shown_page).data(ExpandedRole) is True

    click(shown_page, qtbot, heading(shown_page))
    assert names(shown_page) == FOLDED


def test_opening_hidden_keeps_the_selection_and_moves_no_cover(shown_page, qtbot):
    hide("Birch")
    select(shown_page, "Cedar")
    chosen = []
    shown_page.row_chosen.connect(lambda: chosen.append(True))
    view = shown_page.list_view

    def places():
        return {name: view.rectForIndex(cover(shown_page, name)).topLeft() for name in FOLDED[:3]}

    before = places()
    for _ in range(2):
        click(shown_page, qtbot, heading(shown_page))

        assert selected(shown_page) == ["Cedar"]
        assert view.currentIndex().data() == "Cedar"
        assert shown_page.details_pane.details().deck.metadata.name == "Cedar"
        assert places() == before
    assert chosen == []


def test_folding_the_selected_deck_away_selects_nothing_else(shown_page, qtbot):
    hide("Birch")
    shown_page.toggle_hidden()
    select(shown_page, "Birch")

    click(shown_page, qtbot, heading(shown_page))

    assert selected(shown_page) == []
    assert shown_page.details_pane.details().deck.metadata.name == "Birch"


def test_opening_hidden_scrolls_its_first_cover_into_view(shown_page, qtbot):
    hide("Birch")
    shown_page.resize(1100, 430)

    click(shown_page, qtbot, heading(shown_page))

    view = shown_page.list_view
    qtbot.waitUntil(
        lambda: view.viewport().rect().contains(view.visualRect(cover(shown_page, "Birch")))
    )


def test_a_click_on_a_heading_that_does_not_fold_changes_nothing(shown_page, qtbot):
    pin("Cedar")
    select(shown_page, "Dune")

    click(shown_page, qtbot, heading(shown_page, DECKS))

    assert names(shown_page) == [PINNED, "Cedar", DECKS, "Aurora", "Birch", "Dune"]
    assert selected(shown_page) == ["Dune"]
    assert shown_page.list_view.currentIndex().data() == "Dune"


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


def test_a_click_that_also_activates_toggles_once(single_click_page, qtbot):
    page = single_click_page
    hide("Birch")

    click(page, qtbot, heading(page))
    assert names(page) == OPENED

    click(page, qtbot, heading(page))
    assert names(page) == FOLDED


@pytest.mark.parametrize("button", [Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton])
def test_only_a_left_click_toggles(single_click_page, qtbot, button):
    hide("Birch")

    click(single_click_page, qtbot, heading(single_click_page), button)

    assert names(single_click_page) == FOLDED


def test_a_double_click_toggles_once(shown_page, qtbot):
    hide("Birch")
    view = shown_page.list_view
    pos = view.visualRect(heading(shown_page)).center()

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)

    assert names(shown_page) == OPENED


# -- the keyboard -------------------------------------------------------------


def test_the_arrows_step_over_headings(shown_page, qtbot):
    pin("Cedar")
    select(shown_page, "Cedar")

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Right)
    assert selected(shown_page) == ["Aurora"]

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Up)
    assert selected(shown_page) == ["Cedar"]

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Down)
    assert selected(shown_page) == ["Aurora"]


@pytest.mark.parametrize("decks", [[deck(f"Deck {number:02}") for number in range(30)]])
def test_paging_reaches_both_ends_past_the_headings(shown_page, qtbot):
    pin("Deck 20")
    select(shown_page, "Deck 20")

    for key, last in ((Qt.Key.Key_PageDown, "Deck 29"), (Qt.Key.Key_PageUp, "Deck 20")):
        for _ in range(30):
            qtbot.keyClick(shown_page.list_view, key)
            assert not shown_page.list_view.currentIndex().data(SectionRole)
        if key == Qt.Key.Key_PageUp:
            assert selected(shown_page) == [last]
        else:
            line = shown_page.list_view.visualRect(cover(shown_page, last)).top()
            here = shown_page.list_view.visualRect(shown_page.list_view.currentIndex()).top()
            assert here == line


@pytest.mark.parametrize("decks", [[deck(f"Deck {number:02}") for number in range(30)]])
def test_returning_to_a_shelfs_first_line_shows_its_heading(shown_page, qtbot):
    pin("Deck 20")
    view = shown_page.list_view

    qtbot.keyClick(view, Qt.Key.Key_End)
    qtbot.keyClick(view, Qt.Key.Key_Home)

    assert selected(shown_page) == ["Deck 20"]
    assert view.visualRect(heading(shown_page, PINNED)).top() >= 0


def test_return_toggles_both_ways_and_leaves_the_selection(shown_page, qtbot):
    hide("Birch")
    select(shown_page, "Dune")

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Right)
    assert shown_page.list_view.currentIndex() == heading(shown_page)
    assert selected(shown_page) == ["Dune"]

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Return)
    assert names(shown_page) == OPENED
    assert shown_page.list_view.currentIndex() == heading(shown_page)
    assert selected(shown_page) == ["Dune"]

    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Return)
    assert names(shown_page) == FOLDED
    assert selected(shown_page) == ["Dune"]


def test_a_refresh_with_the_heading_current_keeps_it_and_the_selection(shown_page, qtbot):
    hide("Birch")
    select(shown_page, "Dune")
    qtbot.keyClick(shown_page.list_view, Qt.Key.Key_Right)

    shown_page.refresh()

    assert shown_page.list_view.currentIndex() == heading(shown_page)
    assert selected(shown_page) == ["Dune"]


# -- the session --------------------------------------------------------------


def test_showing_is_kept_through_a_refresh_and_not_by_a_new_page(page):
    hide("Birch")
    page.toggle_hidden()

    page.refresh()

    assert names(page) == OPENED
    another = DeckFilterProxyModel()
    another.setSourceModel(page.decks_model)
    assert "Birch" not in [index.data() for index in rows(another)]


def test_with_every_deck_hidden_the_heading_remains(page):
    hide(*NAMES)

    assert names(page) == [LIBRARY["shelf_hidden"].format(count=4)]
    assert not page.empty_label.isVisibleTo(page)


# -- search -------------------------------------------------------------------


def test_a_search_opens_hidden_for_as_long_as_it_runs(page):
    hide("Birch", "Dune")

    page.set_search("bir")
    assert names(page) == [HIDDEN_ONE, "Birch"]  # it counts what it found
    assert heading(page).data(ExpandedRole) is None
    assert not heading(page).flags() & Qt.ItemFlag.ItemIsEnabled

    page.set_search("")
    assert names(page) == ["Aurora", "Cedar", LIBRARY["shelf_hidden"].format(count=2)]


@pytest.mark.parametrize("entries", [[catalog_entry("aquatic-tarot")]])
def test_a_search_keeps_only_the_headings_of_shelves_it_finds(page):
    pin("Cedar")
    hide("Birch")

    page.set_search("cedar")
    assert names(page) == [PINNED, "Cedar"]

    page.set_search("aquatic")
    assert names(page) == [AVAILABLE, GHOST]


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
def test_hiding_the_last_deck_steps_over_the_heading_to_the_ghost(page):
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

    assert names(page) == ["Aurora", "Dune", LIBRARY["shelf_hidden"].format(count=2)]
    assert selected(page) == ["Dune"]


def test_hiding_the_only_pin_selects_the_cover_after_it(page):
    pin("Cedar")
    select(page, "Cedar")

    trigger(page, "Cedar", LIBRARY["hide_deck"])

    assert selected(page) == ["Aurora"]


def test_hiding_into_an_open_hidden_keeps_the_selection(page):
    hide("Birch")
    page.toggle_hidden()
    select(page, "Dune")

    trigger(page, "Dune", LIBRARY["hide_deck"])

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
