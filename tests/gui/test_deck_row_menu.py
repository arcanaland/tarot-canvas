"""An installed deck's menu, and Remove from Library under an Undo"""

import shutil

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QMenu

from tarot_canvas.models import deck_library as deck_library_module
from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models import library_curation as curation
from tarot_canvas.models.deck_library import DeckLibrary
from tarot_canvas.models.reference_deck import ReferenceDeck
from tarot_canvas.settings import LIBRARY_VIEW_DECKS, LIBRARY_VIEW_SPREADS, get_readings_deck
from tarot_canvas.ui.library.decks.model import DeckRole
from tarot_canvas.ui.library.tab import LibraryTab
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import DECK_VIEW, LIBRARY, READINGS, SPREADS
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tests.conftest import DECK_LIBRARY_CONSUMERS, MINIMAL_DECK_PATH
from tests.gui.test_library_tab import ghost_library, ghost_of, installed, transport  # noqa: F401
from tests.gui.test_spreads_view import store, two_slots

OPEN, START, PIN, HIDE, FOLDER, EXPORT, REMOVE = (
    LIBRARY["open"],
    READINGS["open"],
    SPREADS["pin"],
    LIBRARY["hide_deck"],
    SPREADS["open_folder"],
    DECK_VIEW["export"],
    LIBRARY["remove_deck"],
)


@pytest.fixture
def decks(tmp_path, monkeypatch):
    """A real library over a temp root: a downloaded deck, a handmade one, the reference"""
    root = tmp_path / "tarot" / "decks"
    root.mkdir(parents=True)
    reference = shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "reference")
    shutil.copytree(MINIMAL_DECK_PATH, root / "downloaded")
    handmade = writer.create("Handmade", decks_root=root)
    monkeypatch.setattr(deck_library_module, "get_decks_directory", lambda: [str(root)])
    monkeypatch.setattr(
        ReferenceDeck, "get_reference_deck_path", staticmethod(lambda: str(reference))
    )
    library = DeckLibrary()
    monkeypatch.setattr(deck_library_module, "deck_library", library)
    for module in DECK_LIBRARY_CONSUMERS:
        monkeypatch.setattr(f"{module}.deck_library", library, raising=False)
    return library, root / "downloaded", handmade


@pytest.fixture
def library_tab(qtbot, decks):
    tab = LibraryTab()
    qtbot.addWidget(tab)
    return tab


@pytest.fixture
def window(qtbot, decks):
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_library_tab(LIBRARY_VIEW_DECKS)
    return window


def page_of(tab):
    return tab.decks_page


def index_at(page, path):
    for row in range(page.list_model.rowCount()):
        index = page.list_model.index(row, 0)
        deck = index.data(DeckRole)
        if deck is not None and DeckLibrary.path_key(deck.root_path) == DeckLibrary.path_key(path):
            return index
    return None


def deck_paths(page):
    paths = []
    for row in range(page.list_model.rowCount()):
        deck = page.list_model.index(row, 0).data(DeckRole)
        if deck is not None:
            paths.append(DeckLibrary.path_key(deck.root_path))
    return paths


def items(menu):
    """(text, enabled) of each action, separators as None"""
    return [
        None if action.isSeparator() else (action.text(), action.isEnabled())
        for action in menu.actions()
    ]


def pane_menu(page, index):
    page.list_view.setCurrentIndex(index)
    button = page.details_pane.menu_button
    menu = button.menu()
    menu.aboutToShow.emit()
    return menu


def remove(page, path):
    action = next(a for a in page.row_menu(index_at(page, path)).actions() if a.text() == REMOVE)
    action.trigger()


# -- the menu --------------------------------------------------------------


def test_a_downloaded_deck_can_be_opened_read_shown_and_removed(library_tab, decks):
    _library, downloaded, _handmade = decks
    menu = page_of(library_tab).row_menu(index_at(page_of(library_tab), downloaded))

    assert items(menu) == [
        (OPEN, True),
        (START, True),
        None,
        (PIN, False),  # it has no identifier
        (HIDE, False),
        None,
        (FOLDER, True),
        None,
        (REMOVE, True),
    ]


def test_a_handmade_deck_also_exports(library_tab, decks):
    _library, _downloaded, handmade = decks
    menu = page_of(library_tab).row_menu(index_at(page_of(library_tab), handmade))

    assert (PIN, True) in items(menu)
    assert (HIDE, True) in items(menu)
    assert (EXPORT, True) in items(menu)
    assert items(menu).index((EXPORT, True)) == items(menu).index((FOLDER, True)) + 1


def test_the_reference_deck_shows_remove_disabled(library_tab, decks):
    library, _downloaded, _handmade = decks
    menu = page_of(library_tab).row_menu(
        index_at(page_of(library_tab), library.reference().root_path)
    )

    assert (REMOVE, False) in items(menu)
    assert (EXPORT, True) not in items(menu)


def test_the_panes_menu_is_the_covers(library_tab, decks):
    page = page_of(library_tab)
    for path in (decks[1], decks[2], decks[0].reference().root_path):
        index = index_at(page, path)
        assert items(pane_menu(page, index)) == items(page.row_menu(index))
    button = page.details_pane.menu_button
    assert button.toolTip() == button.accessibleName() == LIBRARY["deck_menu_tooltip"]


def test_reopening_the_panes_menu_does_not_stack_its_items(library_tab, decks):
    page = page_of(library_tab)
    index = index_at(page, decks[1])
    once = items(pane_menu(page, index))
    page.details_pane.menu_button.menu().aboutToShow.emit()

    assert items(page.details_pane.menu_button.menu()) == once


def test_a_ghost_has_no_menu(ghost_library):  # noqa: F811
    page = page_of(ghost_library)
    ghost = ghost_of(ghost_library)

    assert page.row_menu(ghost) is None
    page.list_view.setCurrentIndex(ghost)
    assert not page.details_pane.menu_button.isVisibleTo(page.details_pane)


def test_the_menu_key_opens_the_current_covers_menu(library_tab, decks, monkeypatch):
    page = page_of(library_tab)
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *_args: shown.append(items(menu)))
    index = index_at(page, decks[1])
    page.list_view.setCurrentIndex(index)

    # What Qt sends the focused view for the Menu key, which offscreen never synthesises
    pos = page.list_view.inputMethodQuery(Qt.InputMethodQuery.ImCursorRectangle).center()
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Keyboard, pos, page.list_view.mapToGlobal(pos)
    )
    QApplication.sendEvent(page.list_view, event)

    assert shown == [items(page.row_menu(index))]


def test_start_reading_remembers_the_deck_and_deals_the_spread(library_tab, decks, spreads_base):
    path = store(spreads_base, "1", two_slots())
    page = page_of(library_tab)
    dealt = []
    page.reading_requested.connect(dealt.append)
    menu = page.row_menu(index_at(page, decks[1]))
    spreads = next(a for a in menu.actions() if a.text() == START).menu()
    spreads.aboutToShow.emit()

    next(a for a in spreads.actions() if a.text() == "Two").trigger()

    assert DeckLibrary.path_key(get_readings_deck()) == DeckLibrary.path_key(decks[1])
    assert dealt == [path]
    browse = next(a for a in spreads.actions() if a.text() == READINGS["browse_spreads"])
    browse.trigger()
    assert library_tab.current_list_page() is library_tab.list_pages[LIBRARY_VIEW_SPREADS]


def test_a_folder_that_cannot_open_says_so_inline(library_tab, decks, monkeypatch):
    from tarot_canvas.ui.library.decks import page as page_module

    asked = []
    monkeypatch.setattr(
        page_module.QDesktopServices, "openUrl", lambda url: asked.append(url) or False
    )
    page = page_of(library_tab)

    page.open_folder(page.list_model.index(0, 0).data(DeckRole))

    assert len(asked) == 1
    assert page.message.label.text() == SPREADS["open_folder_failed"]


def test_export_opens_the_decks_view_and_starts_its_export(window, decks, monkeypatch):
    started = []
    monkeypatch.setattr(DeckViewTab, "start_export", lambda tab: started.append(tab.deck_path))
    page = window.find_library_tab().decks_page
    menu = page.row_menu(index_at(page, decks[2]))

    next(a for a in menu.actions() if a.text() == EXPORT).trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, DeckViewTab)
    assert started == [tab.deck_path]


# -- Remove ----------------------------------------------------------------


def test_remove_takes_the_cover_and_undo_brings_it_back_selected(library_tab, decks):
    _library, downloaded, _handmade = decks
    page = page_of(library_tab)
    page.list_view.setCurrentIndex(index_at(page, downloaded))

    remove(page, downloaded)

    assert index_at(page, downloaded) is None
    assert not downloaded.exists()
    assert page.message.label.text() == LIBRARY["deck_removed"].format(name="Minimal Test Deck")
    # The pane moved on rather than offering a deck that is gone
    shown = page.details_pane.details().deck
    assert DeckLibrary.path_key(shown.root_path) != DeckLibrary.path_key(downloaded)

    page.undo_action.trigger()

    assert downloaded.is_dir()
    assert page.current_deck() is not None
    assert DeckLibrary.path_key(page.current_deck().root_path) == DeckLibrary.path_key(downloaded)


def test_a_final_remove_takes_the_folder_and_its_handmade_key(library_tab, decks):
    _library, _downloaded, handmade = decks
    page = page_of(library_tab)
    assert curation.handmade_decks() == {handmade.name}

    remove(page, handmade)
    page.commit_pending_delete()

    assert not handmade.exists()
    assert not handmade.with_name(handmade.name + ".deleted").exists()
    assert curation.handmade_decks() == set()
    assert DeckLibrary.path_key(handmade) not in deck_paths(page)


@pytest.mark.parametrize("change", [curation.set_deck_pinned, curation.set_deck_hidden])
def test_a_final_remove_takes_the_pin_or_hide_and_an_undone_one_keeps_it(
    library_tab, decks, change
):
    library, _downloaded, handmade = decks
    page = page_of(library_tab)
    identifier = library.load(handmade).metadata.identifier
    change(identifier, True)
    page.toggle_hidden()

    remove(page, handmade)
    page.undo_action.trigger()
    assert identifier in curation.deck_pins() | curation.deck_hides()

    remove(page, handmade)
    page.commit_pending_delete()
    assert curation.deck_pins() | curation.deck_hides() == set()


def test_removing_a_deck_folded_away_moves_the_pane_off_it(library_tab, decks):
    library, _downloaded, handmade = decks
    page = page_of(library_tab)
    curation.set_deck_hidden(library.load(handmade).metadata.identifier, True)
    page.toggle_hidden()
    page.select_deck_path(index_at(page, handmade).data(DeckRole).root_path)
    page.toggle_hidden()

    page.remove(page.details_pane.details().deck)

    assert DeckLibrary.path_key(page.details_pane.details().deck.root_path) != (
        DeckLibrary.path_key(handmade)
    )


def test_removing_twins_in_a_row_forgets_the_pin_with_the_second(library_tab, decks):
    library, _downloaded, handmade = decks
    page = page_of(library_tab)
    copy = shutil.copytree(handmade, handmade.with_name("copy"))
    library.rescan()
    identifier = library.load(handmade).metadata.identifier
    curation.set_deck_pinned(identifier, True)

    remove(page, handmade)
    remove(page, copy)  # makes the first final
    assert curation.deck_pins() == {identifier}

    page.commit_pending_delete()
    assert curation.deck_pins() == set()


def test_the_panes_menu_flips_once_the_deck_is_pinned(library_tab, decks):
    library, _downloaded, handmade = decks
    page = page_of(library_tab)
    curation.set_deck_pinned(library.load(handmade).metadata.identifier, True)

    menu = pane_menu(page, index_at(page, handmade))

    assert (SPREADS["unpin"], True) in items(menu)


def test_closing_the_library_makes_a_pending_remove_final(library_tab, decks):
    remove(page_of(library_tab), decks[1])
    library_tab.about_to_close()

    assert not decks[1].exists()
    assert not decks[1].with_name("downloaded.deleted").exists()


def test_the_reference_deck_is_never_removed(library_tab, decks):
    library = decks[0]
    page = page_of(library_tab)

    page.remove(library.reference())

    assert DeckLibrary.path_key(library.reference().root_path) in deck_paths(page)
    assert page.staged is None


def test_remove_closes_the_decks_tabs_and_shows_the_undo(window, decks):
    library, downloaded, _handmade = decks
    deck = library.load(downloaded)
    window.new_deck_view_tab(deck_path=str(downloaded))
    window.open_card_view_tab(deck.cards[0], deck)
    library_tab = window.find_library_tab()

    remove(library_tab.decks_page, downloaded)

    tabs = [window.tab_widget.widget(i) for i in range(window.tab_widget.count())]
    assert not any(isinstance(tab, DeckViewTab) for tab in tabs)
    assert not any(getattr(tab, "card", None) is not None for tab in tabs)
    assert window.tab_widget.currentWidget() is library_tab
    assert library_tab.decks_page.staged is not None


def test_a_deck_view_still_writing_stops_remove(window, decks, monkeypatch):
    _library, _downloaded, handmade = decks
    tab = window.new_deck_view_tab(deck_path=str(handmade))
    monkeypatch.setattr(tab.editor, "is_busy", lambda: True)

    remove(window.find_library_tab().decks_page, handmade)

    assert handmade.is_dir()
    assert window.tab_widget.indexOf(tab) != -1
    assert window.find_library_tab().decks_page.staged is None


def test_a_tab_that_refuses_to_close_stops_remove(window, decks, monkeypatch):
    _library, downloaded, _handmade = decks
    tab = window.new_deck_view_tab(deck_path=str(downloaded))
    monkeypatch.setattr(window, "confirm_close", lambda closing: closing is not tab)

    remove(window.find_library_tab().decks_page, downloaded)

    assert downloaded.is_dir()
    assert window.tab_widget.indexOf(tab) != -1


def test_a_removed_catalog_decks_rescan_is_announced_once(library_tab, decks, qtbot):
    from tarot_canvas.models.deck_events import deck_events

    fired = []
    deck_events().decks_changed.connect(lambda: fired.append(True))

    remove(page_of(library_tab), decks[1])
    assert fired == [True]
    page_of(library_tab).undo_action.trigger()
    assert fired == [True, True]
