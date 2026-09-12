from contextlib import contextmanager
from pathlib import Path

from PyQt6.QtCore import QEvent, QItemSelectionModel, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.catalog import is_installed
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    LIBRARY_DENSITY_DEFAULT,
    LIBRARY_DENSITY_KEY,
    LIBRARY_DETAILS_PANE_DEFAULT,
    LIBRARY_DETAILS_PANE_KEY,
    LIBRARY_SORT_DEFAULT,
    LIBRARY_SORT_KEY,
    get_settings,
    record_deck_opened,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.library.deck_delegate import DeckDelegate
from tarot_canvas.ui.library.deck_details import details_for
from tarot_canvas.ui.library.deck_details_pane import DeckDetailsPane
from tarot_canvas.ui.library.deck_downloads import deck_downloads
from tarot_canvas.ui.library.deck_model import (
    SORT_AUTHOR,
    SORT_COUNT,
    SORT_NAME,
    SORT_RECENT,
    DeckFilterProxyModel,
    DeckListModel,
    DeckRole,
    EntryRole,
)
from tarot_canvas.ui.tabs.base_tab import BaseTab

SORT_CHOICES = [
    ("Name", SORT_NAME),
    ("Author", SORT_AUTHOR),
    ("Card count", SORT_COUNT),
    ("Recently opened", SORT_RECENT),
]

DENSITY_CHOICES = [
    ("Small", units.DENSITY_SMALL),
    ("Medium", units.DENSITY_MEDIUM),
    ("Large", units.DENSITY_LARGE),
]


class LibraryTab(BaseTab):
    deck_selected = pyqtSignal(object)  # Signal when a deck is selected

    DETAILS_PANE_MIN_WIDTH = 16 * units.GRID_UNIT
    DETAILS_PANE_SHARE = 0.3  # of the tab's width, the first time it opens

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        # Whether selection opens the details pane: False once the user has closed it
        self._details_wanted = self.settings.value(
            LIBRARY_DETAILS_PANE_KEY, LIBRARY_DETAILS_PANE_DEFAULT, type=bool
        )
        self._details_width = 0  # for the session, as the card view keeps its own
        self._programmatic = 0  # nesting depth of selection the user didn't make
        self.setup_ui()

        # App-wide signals reach only slots, so Qt drops each connection when the tab is deleted
        deck_events().decks_changed.connect(self.refresh)
        catalog = deck_catalog()
        catalog.entries_changed.connect(self.on_entries_changed)
        catalog.cover_ready.connect(self.model.cover_ready)
        deck_downloads().changed.connect(self.model.download_changed)
        catalog.activate()

        # Set the tab icon after a short delay to ensure the tab is added
        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.model = DeckListModel(
            deck_manager.get_all_decks(), parent=self, entries=deck_catalog().entries()
        )
        self.proxy_model = DeckFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        self.layout.addWidget(self._build_header())

        grid = QWidget()
        column = QVBoxLayout(grid)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_view())
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)
        column.addWidget(self.empty_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(grid)
        self.splitter.addWidget(self._build_details())
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        # The grid takes a window's growth; the pane keeps the width it was given
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.layout.addWidget(self.splitter, 1)
        self.details_container.hide()

        # Not a bare I: the grid's type-ahead search takes letters
        shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.details_toggle.click)

        self._restore_settings()
        self._update_empty_state()
        self._sync_details_toggle()

    def _build_header(self):
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(
            units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING
        )
        row.setSpacing(units.LARGE_SPACING)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search decks…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.addAction(
            QIcon.fromTheme("search"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_field.textChanged.connect(self.on_search_changed)
        row.addWidget(self.search_field, 1)

        self.sort_combo = QComboBox()
        for label, key in SORT_CHOICES:
            self.sort_combo.addItem(label, key)
        self.sort_combo.setToolTip("Sort decks")
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
        row.addWidget(self.sort_combo)

        self.density_combo = QComboBox()
        for label, key in DENSITY_CHOICES:
            self.density_combo.addItem(label, key)
        self.density_combo.setToolTip("Cover size")
        self.density_combo.currentIndexChanged.connect(self.on_density_changed)
        row.addWidget(self.density_combo)

        self.add_deck_button = QToolButton()
        self.add_deck_button.setText("Add Deck…")
        self.add_deck_button.setIcon(QIcon.fromTheme("list-add"))
        self.add_deck_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add_deck_button.clicked.connect(self.browse_for_deck)
        row.addWidget(self.add_deck_button)

        self.details_toggle = QToolButton()
        self.details_toggle.setCheckable(True)
        self.details_toggle.clicked.connect(self.toggle_details_pane)
        row.addWidget(self.details_toggle)

        return header

    def _build_view(self):
        self.view = QListView()
        self.view.setModel(self.proxy_model)
        self.delegate = DeckDelegate(self.view)
        self.view.setItemDelegate(self.delegate)

        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setFlow(QListView.Flow.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(units.LARGE_SPACING)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.view.setMouseTracking(True)

        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.view.activated.connect(self.on_deck_activated)
        self.view.clicked.connect(self.on_deck_clicked)
        self.view.selectionModel().currentChanged.connect(self.on_current_changed)
        self.proxy_model.modelReset.connect(self._update_empty_state)
        self.proxy_model.rowsInserted.connect(self._update_empty_state)
        self.proxy_model.rowsRemoved.connect(self._update_empty_state)

        # The source's, not the proxy's, so a row the search hides still updates the pane
        self.model.dataChanged.connect(self._on_rows_changed)
        self.model.modelReset.connect(self._follow_shown_deck)

        # A click on no deck deselects, which a single-selection view doesn't do itself,
        # and so does Esc. The pane keeps showing the deck it showed.
        self.view.viewport().installEventFilter(self)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.view)
        escape.setContext(Qt.ShortcutContext.WidgetShortcut)
        escape.activated.connect(self.clear_selection)

        return self.view

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and watched is self.view.viewport()
            and not self.view.indexAt(event.position().toPoint()).isValid()
        ):
            self.clear_selection()
        return super().eventFilter(watched, event)

    def clear_selection(self):
        """Nothing selected and nothing current, so a refresh doesn't reselect it"""
        self.view.selectionModel().clear()

    def _build_details(self):
        self.details_container = QWidget()
        row = QHBoxLayout(self.details_container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # A line for the splitter handle to sit on, as the card view draws it
        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)
        row.addWidget(seam)

        self.details_pane = DeckDetailsPane()
        self.details_pane.open_requested.connect(self.on_deck_selected)
        self.details_pane.download_requested.connect(self._start_download)
        self.details_pane.cancel_requested.connect(self._cancel_download)
        row.addWidget(self.details_pane, 1)

        self.details_container.setMinimumWidth(self.DETAILS_PANE_MIN_WIDTH)
        return self.details_container

    # -- settings ---------------------------------------------------------

    def _restore_settings(self):
        density = self.settings.value(LIBRARY_DENSITY_KEY, LIBRARY_DENSITY_DEFAULT, type=str)
        index = self.density_combo.findData(density)
        self.density_combo.setCurrentIndex(index if index >= 0 else 1)

        sort_key = self.settings.value(LIBRARY_SORT_KEY, LIBRARY_SORT_DEFAULT, type=str)
        index = self.sort_combo.findData(sort_key)
        self.sort_combo.setCurrentIndex(index if index >= 0 else 0)

        # setCurrentIndex only emits when the index actually moves, so apply
        # both explicitly rather than relying on the signals above.
        self._apply_density(self.density_combo.currentData())
        self.proxy_model.set_sort_key(self.sort_combo.currentData())

    def _apply_density(self, density):
        if self.delegate.set_density(density):
            self.view.setGridSize(QSize())
            self.view.reset()
            self.view.scheduleDelayedItemsLayout()

    # -- slots ------------------------------------------------------------

    def on_search_changed(self, text):
        self.proxy_model.setFilterFixedString(text)
        self._update_empty_state()

    def on_sort_changed(self):
        key = self.sort_combo.currentData()
        self.proxy_model.set_sort_key(key)
        self.settings.setValue(LIBRARY_SORT_KEY, key)

    def on_density_changed(self):
        density = self.density_combo.currentData()
        self._apply_density(density)
        self.settings.setValue(LIBRARY_DENSITY_KEY, density)

    def on_current_changed(self, current, _previous):
        # Invalid when the search hides the selection: the pane keeps showing that deck
        if not current.isValid():
            return
        self._show_details(current)
        # The keyboard's path; a click's is on_deck_clicked. Not selected is the view
        # marking a first deck current as it takes focus, which is no one's selection.
        selected = self.view.selectionModel().isSelected(current)
        if self.view.hasFocus() and selected and not self._programmatic:
            self._open_details_for_selection()

        deck = current.data(DeckRole)
        if deck is not None:
            self.deck_selected.emit(deck)

    def on_deck_clicked(self, index):
        self._show_details(index)
        self._open_details_for_selection()

    def on_deck_activated(self, index):
        deck = index.data(DeckRole)
        if deck is not None:
            self.on_deck_selected(deck)
            return
        if index.data(EntryRole) is not None:
            self._reveal_ghost(index)

    def _reveal_ghost(self, index):
        """Show a ghost's details with Download focused, even if the user closed the pane.

        The pane is the only way to download, so it opens; the download never starts
        here, so the licence is on screen before any of the deck is on disk.
        """
        self._show_details(index)
        self._set_details_open(True)
        self.details_pane.focus_action()

    def _start_download(self, entry):
        deck_downloads().start(entry)

    def _cancel_download(self, slug):
        deck_downloads().cancel(slug)

    # -- the details pane -------------------------------------------------

    def details_pane_is_open(self):
        return not self.details_container.isHidden()

    def toggle_details_pane(self):
        """The one control that closes the pane, so a close here is remembered"""
        want = not self.details_pane_is_open()
        if want and self.details_pane.details() is None:
            return
        self._details_wanted = want
        self.settings.setValue(LIBRARY_DETAILS_PANE_KEY, want)
        self._set_details_open(want)

    def _open_details_for_selection(self):
        if self._details_wanted:
            self._set_details_open(True)

    def _set_details_open(self, want):
        if want != self.details_pane_is_open():
            sizes = self.splitter.sizes()
            total = sum(sizes) or self.width()
            if want:
                width = self._details_width or round(total * self.DETAILS_PANE_SHARE)
                self.details_container.show()
                self.splitter.setSizes([max(0, total - width), width])
            else:
                self._details_width = sizes[1] or self._details_width
                self.details_container.hide()
        self._sync_details_toggle()

    def _sync_details_toggle(self):
        """Keep the toggle saying what the next press will do"""
        is_open = self.details_pane_is_open()
        # Disabled until there's a deck to show, so the pane never opens empty
        self.details_toggle.setEnabled(self.details_pane.details() is not None)
        self.details_toggle.setChecked(is_open)
        if is_open:
            self.details_toggle.setIcon(QIcon.fromTheme("sidebar-collapse-right"))
            self.details_toggle.setToolTip("Hide deck details (Ctrl+I)")
        else:
            self.details_toggle.setIcon(QIcon.fromTheme("sidebar-expand-right"))
            self.details_toggle.setToolTip("Show deck details (Ctrl+I)")

    def _show_details(self, index):
        self.details_pane.show_details(details_for(index))
        self._sync_details_toggle()

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
            return self._source_row(_is_deck_at(shown.deck.deck_path))
        ghost = self._source_row(_is_ghost_of(shown.entry))
        if ghost is not None:
            return ghost
        return self._source_row(_is_installed_copy_of(shown.entry))

    def _source_row(self, matches):
        for row in range(self.model.rowCount()):
            index = self.model.index(row, 0)
            if matches(index):
                return index
        return None

    def on_deck_selected(self, deck):
        """Open the deck in a new tab."""
        record_deck_opened(deck.deck_path)
        self.proxy_model.refresh_recent()

        main_window = self.window()
        if hasattr(main_window, "new_deck_view_tab"):
            main_window.new_deck_view_tab(deck_path=deck.deck_path)

    def browse_for_deck(self):
        """Open file dialog to browse for additional decks"""
        main_window = self.window()
        if hasattr(main_window, "open_deck"):
            main_window.open_deck()

    @pyqtSlot()
    def refresh(self):
        """Reload the deck list, keeping the selected deck selected if it survives."""
        with self._selection_kept():
            self.model.set_decks(deck_manager.get_all_decks())
            self.proxy_model.refresh_recent()

    @pyqtSlot()
    def on_entries_changed(self):
        with self._selection_kept():
            self.model.set_entries(deck_catalog().entries())

    @contextmanager
    def _selection_kept(self):
        """Reselect the current deck after a reset; a ghost that installed, as its deck."""
        current = self.view.currentIndex()
        deck = current.data(DeckRole) if current.isValid() else None
        entry = current.data(EntryRole) if current.isValid() else None
        with self._programmatic_selection():
            yield
            if deck is not None:
                self.select_deck_path(deck.deck_path)
            elif entry is not None and not self._select_first(_is_ghost_of(entry)):
                self._select_first(_is_installed_copy_of(entry))
        self._update_empty_state()

    @contextmanager
    def _programmatic_selection(self):
        """Selection the user didn't make, which never opens the details pane"""
        self._programmatic += 1
        try:
            yield
        finally:
            self._programmatic -= 1

    def current_deck(self):
        index = self.view.currentIndex()
        return index.data(DeckRole) if index.isValid() else None

    def select_deck_path(self, deck_path):
        return self._select_first(_is_deck_at(deck_path))

    def _select_first(self, matches):
        for row in range(self.proxy_model.rowCount()):
            index = self.proxy_model.index(row, 0)
            if matches(index):
                with self._programmatic_selection():
                    self.view.selectionModel().setCurrentIndex(
                        index, QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
                return True
        return False

    def _update_empty_state(self):
        empty = self.proxy_model.rowCount() == 0
        if empty:
            self.empty_label.setText(
                "No decks match your search."
                if self.model.rowCount()
                else "No decks installed yet. Use Add Deck… to install one."
            )
        self.empty_label.setVisible(empty)
        self.view.setVisible(not empty)

    def update_tab_icon(self):
        """Update the tab with a library icon"""
        parent = self.parent()
        if not parent:
            return

        # Try to find a parent that has setTabIcon method
        tab_widget = None
        parent_widget = parent
        while parent_widget and not tab_widget:
            if hasattr(parent_widget, "setTabIcon"):
                tab_widget = parent_widget
                break
            parent_widget = parent_widget.parent()

        if not tab_widget:
            return

        index = tab_widget.indexOf(self)
        if index < 0:
            return

        icon = QIcon.fromTheme(
            "folder-bookmarks",
            QIcon(
                str(Path(__file__).parent.parent.parent / "resources" / "icons" / "bookmarks.png")
            ),
        )
        tab_widget.setTabIcon(index, icon)


def _is_deck_at(deck_path):
    def matches(index):
        deck = index.data(DeckRole)
        return deck is not None and deck.deck_path == deck_path

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
