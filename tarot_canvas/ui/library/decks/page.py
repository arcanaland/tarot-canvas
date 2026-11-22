import logging
import os
from contextlib import contextmanager
from pathlib import Path

from PyQt6.QtCore import QItemSelectionModel, QModelIndex, QSize, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QAbstractItemView, QListView

from tarot_canvas.models import library_curation as curation
from tarot_canvas.models.catalog import is_installed
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.deck_library import deck_library, is_removable
from tarot_canvas.settings import (
    LIBRARY_SORT_DEFAULT,
    LIBRARY_SORT_KEY,
    get_settings,
    record_deck_opened,
    set_readings_deck,
)
from tarot_canvas.ui import units
from tarot_canvas.ui.catalog.client import deck_catalog
from tarot_canvas.ui.catalog.downloads import deck_downloads
from tarot_canvas.ui.library.decks.delegate import DeckDelegate
from tarot_canvas.ui.library.decks.details import details_for
from tarot_canvas.ui.library.decks.details_pane import DeckDetailsPane
from tarot_canvas.ui.library.decks.grid import DeckGrid
from tarot_canvas.ui.library.decks.model import (
    HIDDEN_SHELF,
    SORT_AUTHOR,
    SORT_RECENT,
    DeckFilterProxyModel,
    DeckListModel,
    DeckRole,
    EntryRole,
    ShelfRole,
)
from tarot_canvas.ui.library.decks.row_menu import deck_row_menu, fill_deck_menu
from tarot_canvas.ui.library.deletable_page import DeletableListPage
from tarot_canvas.ui.library.roles import SORT_COUNT, SORT_NAME
from tarot_canvas.ui.library.section_row import is_section
from tarot_canvas.ui.strings import LIBRARY, SPREADS

log = logging.getLogger(__name__)

SORT_CHOICES = [
    (LIBRARY["sort_name"], SORT_NAME),
    (LIBRARY["sort_author"], SORT_AUTHOR),
    (LIBRARY["sort_count"], SORT_COUNT),
    (LIBRARY["sort_recent"], SORT_RECENT),
]


class DecksPage(DeletableListPage):
    """Covers on shelves: the installed decks, the catalog's not yet installed, then the hidden"""

    DETAILS_BESIDE = True
    LIST_VIEW = DeckGrid

    deck_selected = pyqtSignal(object)  # the Deck made current
    open_requested = pyqtSignal(object)  # the Deck to open in a tab
    details_requested = pyqtSignal()
    row_chosen = pyqtSignal()
    reading_requested = pyqtSignal(object)  # the spread's folder, dealt with the remembered deck
    browse_spreads_requested = pyqtSignal()
    export_requested = pyqtSignal(object)  # the Deck

    def __init__(self, parent=None, spread_menu=None):
        """spread_menu(parent, start, browse) builds the spreads a reading can start from"""
        settings = get_settings()
        decks_model = DeckListModel(deck_library.decks(), entries=deck_catalog().entries())
        proxy = DeckFilterProxyModel()
        proxy.setSourceModel(decks_model)
        proxy.set_sort_key(settings.value(LIBRARY_SORT_KEY, LIBRARY_SORT_DEFAULT, type=str))
        super().__init__(
            proxy,
            DeckDelegate,
            DeckDetailsPane(),
            parent,
            texts={
                "deleted": LIBRARY["deck_removed"],
                "delete_failed": LIBRARY["deck_remove_failed"],
                "restore_failed": LIBRARY["deck_restore_failed"],
            },
        )
        # The library forgets or finds the folder, and its rescan tells every view
        self.folders_changed.connect(deck_library.rescan)
        self.settings = settings
        self.spread_menu = spread_menu
        self.decks_model = decks_model
        self.decks_model.setParent(self)
        self._programmatic = 0  # nesting depth of selection the user didn't make
        self._removed = {}  # identifier by folder: a final Remove has no deck.toml left to read

        self.details_pane.open_requested.connect(self.open_deck)
        self.details_pane.download_requested.connect(self._start_download)
        self.details_pane.cancel_requested.connect(self._cancel_download)
        self.details_pane.menu_requested.connect(self._fill_pane_menu)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._on_context_menu)

        self.list_model.modelReset.connect(self._update_empty_state)
        self.list_model.rowsInserted.connect(self._update_empty_state)
        self.list_model.rowsRemoved.connect(self._update_empty_state)
        # The source's, not the proxy's, so a row the search hides still updates the pane
        self.decks_model.dataChanged.connect(self._on_rows_changed)
        self.decks_model.modelReset.connect(self._follow_shown_deck)
        self._update_empty_state()

        # App-wide signals reach only slots, so Qt drops each connection when the page is deleted
        deck_events().decks_changed.connect(self.refresh)
        catalog = deck_catalog()
        catalog.entries_changed.connect(self.on_entries_changed)
        catalog.cover_ready.connect(self.decks_model.cover_ready)
        deck_downloads().changed.connect(self.decks_model.download_changed)
        catalog.activate()

    def _build_list(self, delegate_class):
        view = super()._build_list(delegate_class)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setFlow(QListView.Flow.LeftToRight)
        view.setWrapping(True)
        view.setMovement(QListView.Movement.Static)
        view.setUniformItemSizes(False)  # for the headings
        view.setSpacing(units.LARGE_SPACING)
        view.setAlternatingRowColors(False)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        view.clicked.connect(self._on_clicked)
        view.heading_clicked.connect(self.toggle_hidden)
        return view

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        return LIBRARY["search_decks"]

    def details_toggle_tooltip(self, is_open):
        return LIBRARY["hide_details" if is_open else "show_details"]

    def sort_choices(self):
        return SORT_CHOICES

    def sort_tooltip(self):
        return LIBRARY["sort_tooltip"]

    def sort_key(self):
        return self.list_model.sort_key()

    def set_sort_key(self, key):
        self.list_model.set_sort_key(key)
        self.settings.setValue(LIBRARY_SORT_KEY, key)

    def set_search(self, text):
        self.list_model.setFilterFixedString(text)
        self._update_empty_state()
        # A heading the search keeps may have changed its count or lost its arrow
        self.list_view.viewport().update()

    def set_density(self, density):
        if self.row_delegate.set_density(density):
            self.list_view.setGridSize(QSize())
            self.list_view.reset()
            self.list_view.scheduleDelayedItemsLayout()

    # -- the decks --------------------------------------------------------

    def current_deck(self):
        index = self._cover_in_hand()
        return index.data(DeckRole) if index.isValid() else None

    def select_deck_path(self, deck_path):
        return self._select_first(_is_deck_at(deck_path))

    def select(self, path):
        return self.select_deck_path(path)

    def open_deck(self, deck):
        record_deck_opened(deck.root_path)
        self.list_model.refresh_recent()
        self.open_requested.emit(deck)

    def start_reading(self, deck, spread_path):
        set_readings_deck(deck.root_path)
        self.reading_requested.emit(spread_path)

    def open_folder(self, deck):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(deck.root_path))):
            log.error("Could not open the folder %s", deck.root_path)
            self.message.show_message(SPREADS["open_folder_failed"])

    # -- the cover's menu ---------------------------------------------------

    def row_menu(self, index):
        """The cover's menu, or None for a ghost"""
        deck = index.data(DeckRole) if index.isValid() else None
        return None if deck is None else deck_row_menu(self, deck, self)

    def _on_context_menu(self, pos):
        menu = self.row_menu(self.list_view.indexAt(pos))
        if menu is not None:
            menu.exec(self.list_view.viewport().mapToGlobal(pos))
            menu.deleteLater()

    def _fill_pane_menu(self, menu, deck):
        fill_deck_menu(menu, deck, self)

    # -- removing, undoably -------------------------------------------------

    def remove(self, deck):
        """Take deck out of the Library under an Undo, once no tab shows it"""
        if not is_removable(deck):
            log.error("Refusing to remove %s, which the app did not install", deck.root_path)
            return
        main_window = self.window()
        if hasattr(main_window, "close_deck"):
            if not main_window.close_deck(deck.root_path):
                return
            # Where the Undo is
            library = main_window.find_library_tab()
            if library is not None:
                main_window.tab_widget.setCurrentWidget(library)
        shown = self.details_pane.details()
        row = self._row_of(deck.root_path)
        neighbours = self._neighbours(self.list_model.rowCount() if row is None else row)
        text = self._texts["deleted"].format(name=deck.metadata.name)
        if not self.delete(deck.root_path, text):
            return
        self._removed[Path(deck.root_path)] = deck.metadata.identifier
        # The pane would go on offering a deck that is no longer there
        shown_deck = shown.deck if shown is not None else None
        if shown_deck is not None and _same_path(shown_deck.root_path, deck.root_path):
            self._select_neighbour(neighbours)

    def _forget(self, path):
        curation.forget_deck(path, self._removed.pop(path, None))

    def _row_of(self, deck_path):
        for row in range(self.list_model.rowCount()):
            if _is_deck_at(deck_path)(self.list_model.index(row, 0)):
                return row
        return None

    def _neighbours(self, row):
        """What finds each cover after row, nearest first, then each before it"""
        found = []
        for near in (*range(row + 1, self.list_model.rowCount()), *reversed(range(row))):
            index = self.list_model.index(near, 0)
            deck, entry = index.data(DeckRole), index.data(EntryRole)
            if deck is not None:
                found.append(_is_deck_at(deck.root_path))
            elif entry is not None:
                found.append(_is_ghost_of(entry))
        return found

    def _select_neighbour(self, neighbours):
        """The first still in the grid. By cover, not row: headings come and go"""
        return any(self._select_first(matches) for matches in neighbours)

    @pyqtSlot()
    def toggle_hidden(self):
        """Open or fold Hidden"""
        with self._programmatic_selection():
            self.list_model.toggle_hidden()
        for row in range(self.list_model.rowCount()):
            index = self.list_model.index(row, 0)
            if index.data(ShelfRole) == HIDDEN_SHELF and not is_section(index):
                # It opens at the grid's end, often below the fold
                self.list_view.scrollTo(index)
                break

    def _start_download(self, entry):
        deck_downloads().start(entry)

    def _cancel_download(self, slug):
        deck_downloads().cancel(slug)

    @pyqtSlot()
    def refresh(self):
        """Reload the deck list, keeping the selected deck selected if it survives."""
        with self._selection_kept():
            self.decks_model.set_decks(deck_library.decks())
            self.list_model.refresh_recent()

    @pyqtSlot()
    def on_entries_changed(self):
        with self._selection_kept():
            self.decks_model.set_entries(deck_catalog().entries())

    # -- what a page fills in -----------------------------------------------

    def _details_for(self, index):
        return None if is_section(index) else details_for(index)

    def _on_activated(self, index):
        if is_section(index):
            if _folds(index):
                self.toggle_hidden()
            return
        deck = index.data(DeckRole)
        if deck is not None:
            self.open_deck(deck)
            return
        if index.data(EntryRole) is not None:
            # A ghost has nothing to open, so Return reveals its Download
            self._show_details(index)
            self.details_requested.emit()
            self.details_pane.focus_action()

    def _on_clicked(self, _index):
        self.row_chosen.emit()

    def _on_current_changed(self, current, _previous):
        # Invalid when the search hides the selection: the pane keeps showing that deck
        if not current.isValid():
            return
        self._show_details(current)
        # The keyboard path
        selected = self.list_view.selectionModel().isSelected(current)
        if self.list_view.hasFocus() and selected and not self._programmatic:
            self.row_chosen.emit()

        deck = current.data(DeckRole)
        if deck is not None:
            self.deck_selected.emit(deck)

    def _update_empty_state(self):
        empty = self.list_model.rowCount() == 0
        if empty:
            self.empty_label.setText(
                LIBRARY["empty_no_match"]
                if self.decks_model.rowCount()
                else LIBRARY["empty_no_decks"]
            )
        self.empty_label.setVisible(empty)
        self.list_view.setVisible(not empty)

    # -- keeping the pane on its deck -------------------------------------

    def _on_rows_changed(self, top, bottom, *_roles):
        index = self._shown_row()
        if index is not None and top.row() <= index.row() <= bottom.row():
            self._show_details(index)

    def _follow_shown_deck(self):
        """Re-read the shown deck after a reset, following a ghost into its installed deck.

        A deck that has gone altogether stays shown as it was.
        """
        index = self._shown_row()
        if index is not None:
            self._show_details(index)

    def _shown_row(self):
        """The source model's row for the deck the pane shows, or None"""
        shown = self.details_pane.details()
        if shown is None:
            return None
        if shown.deck is not None:
            return self._source_row(_is_deck_at(shown.deck.root_path))
        ghost = self._source_row(_is_ghost_of(shown.entry))
        if ghost is not None:
            return ghost
        return self._source_row(_is_installed_copy_of(shown.entry))

    def _source_row(self, matches):
        for row in range(self.decks_model.rowCount()):
            index = self.decks_model.index(row, 0)
            if matches(index):
                return index
        return None

    # -- selection --------------------------------------------------------

    def _cover_in_hand(self):
        """The current cover, or the selected one while a heading is current"""
        current = self.list_view.currentIndex()
        if not is_section(current):
            return current
        return next(iter(self.list_view.selectedIndexes()), QModelIndex())

    @contextmanager
    def _selection_kept(self):
        on_heading = is_section(self.list_view.currentIndex())
        cover = self._cover_in_hand()
        deck = cover.data(DeckRole) if cover.isValid() else None
        entry = cover.data(EntryRole) if cover.isValid() else None
        neighbours = self._neighbours(cover.row()) if deck is not None else []
        with self._programmatic_selection():
            yield
            if deck is not None:
                if not self.select_deck_path(deck.root_path) and self._is_hidden(deck.root_path):
                    self._select_neighbour(neighbours)
            elif entry is not None and not self._select_first(_is_ghost_of(entry)):
                self._select_first(_is_installed_copy_of(entry))
            if on_heading:
                # Current for the keyboard, but never selected
                self._select_first(_folds, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._update_empty_state()

    @contextmanager
    def _programmatic_selection(self):
        self._programmatic += 1
        try:
            yield
        finally:
            self._programmatic -= 1

    def _is_hidden(self, deck_path):
        index = self._source_row(_is_deck_at(deck_path))
        return index is not None and index.data(ShelfRole) == HIDDEN_SHELF

    def _select_first(self, matches, flag=QItemSelectionModel.SelectionFlag.ClearAndSelect):
        for row in range(self.list_model.rowCount()):
            index = self.list_model.index(row, 0)
            if matches(index):
                with self._programmatic_selection():
                    self.list_view.selectionModel().setCurrentIndex(index, flag)
                return True
        return False


def _same_path(a, b):
    return os.fspath(a) == os.fspath(b)


def _folds(index):
    return is_section(index) and bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)


def _is_deck_at(deck_path):
    def matches(index):
        deck = index.data(DeckRole)
        return deck is not None and _same_path(deck.root_path, deck_path)

    return matches


def _is_ghost_of(entry):
    def matches(index):
        ghost = index.data(EntryRole)
        return ghost is not None and ghost.slug == entry.slug

    return matches


def _is_installed_copy_of(entry):
    def matches(index):
        deck = index.data(DeckRole)
        return deck is not None and is_installed(entry, deck)

    return matches
