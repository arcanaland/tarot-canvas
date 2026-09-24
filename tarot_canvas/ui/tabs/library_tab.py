from contextlib import contextmanager

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
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
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
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_DEFAULT,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEWS,
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
from tarot_canvas.ui.library.notes_page import NotesPage
from tarot_canvas.ui.library.notes_text import text as notes_text
from tarot_canvas.ui.tabs.base_tab import BaseTab

# The deck view's name. The notes view takes its own from notes_text, which is where
# every string this view adds belongs.
DECKS_VIEW_NAME = "Decks"
SEARCH_DECKS_PLACEHOLDER = "Search decks…"

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

        grid = QWidget()
        column = QVBoxLayout(grid)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_view())
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)
        column.addWidget(self.empty_label)

        self.notes_page = NotesPage(deck_manager.get_reference_deck())
        self.notes_page.card_activated.connect(self.on_card_activated)
        self.notes_page.details_changed.connect(self._sync_details_toggle)

        # One page per sidebar row, in LIBRARY_VIEWS order
        self.pages = QStackedWidget()
        self.pages.addWidget(grid)
        self.pages.addWidget(self.notes_page)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.pages)
        self.splitter.addWidget(self._build_details())
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        # The grid takes a window's growth; the pane keeps the width it was given
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.details_container.hide()

        # [sidebar | header over (seam | splitter)]. The sidebar and header share the window
        # colour, so the seam starts below the header, as the details pane's does
        below_header = QHBoxLayout()
        below_header.setContentsMargins(0, 0, 0, 0)
        below_header.setSpacing(0)
        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)
        below_header.addWidget(seam)
        below_header.addWidget(self.splitter, 1)

        content = QWidget()
        content_column = QVBoxLayout(content)
        content_column.setContentsMargins(0, 0, 0, 0)
        content_column.setSpacing(0)
        self.header = self._build_header()
        content_column.addWidget(self.header)
        content_column.addLayout(below_header, 1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(content, 1)
        self.layout.addLayout(body, 1)

        # The sidebar first, so Tab goes from choosing a view to searching it
        QWidget.setTabOrder(self.sidebar, self.search_field)

        # Not a bare I: the grid's type-ahead search takes letters
        shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.details_toggle.click)

        self._restore_settings()
        self.sidebar.currentRowChanged.connect(self.on_view_changed)
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
        self.search_field.setPlaceholderText(SEARCH_DECKS_PLACEHOLDER)
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

        # Opens a deck folder where it is; it installs nothing, so not "Add"
        self.open_deck_button = QToolButton()
        self.open_deck_button.setText("Open Deck…")
        # Not document-open, which the details pane's Open uses on the same screen
        self.open_deck_button.setIcon(QIcon.fromTheme("document-open-folder"))
        self.open_deck_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_deck_button.clicked.connect(self.browse_for_deck)
        row.addWidget(self.open_deck_button)

        self.details_toggle = QToolButton()
        self.details_toggle.setCheckable(True)
        self.details_toggle.clicked.connect(self.toggle_details_pane)
        row.addWidget(self.details_toggle)

        return header

    def _view_rows(self):
        """(view, name, theme icon) per sidebar row, in LIBRARY_VIEWS order"""
        return [
            (LIBRARY_VIEW_DECKS, DECKS_VIEW_NAME, "view-list-icons"),
            (LIBRARY_VIEW_NOTES, notes_text("view_name"), "view-pim-notes"),
        ]

    def _build_sidebar(self):
        """One row per view (inspired by Dolphin's Places panel)"""
        self.sidebar = QListWidget()
        self.sidebar.setViewMode(QListView.ViewMode.ListMode)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.viewport().setAutoFillBackground(False)
        self.sidebar.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setSpacing(units.SMALL_SPACING // 2)

        for view, name, icon in self._view_rows():
            item = QListWidgetItem(QIcon.fromTheme(icon), name)
            item.setData(Qt.ItemDataRole.UserRole, view)
            self.sidebar.addItem(item)

        # A click on no row, or a Ctrl+click on the current one, must not leave no view chosen
        self.sidebar.itemSelectionChanged.connect(self._keep_a_view_selected)

        self.sidebar.setFixedWidth(
            self.sidebar.sizeHintForColumn(0) + 2 * units.LARGE_SPACING + units.GRID_UNIT
        )

        # Center the first row on the header row
        spacing = self.sidebar.spacing()
        row_height = self.sidebar.sizeHintForRow(0)
        top = self.header.sizeHint().height() // 2 - row_height // 2 - spacing
        self.sidebar.setViewportMargins(0, max(0, top), 0, 0)
        return self.sidebar

    def _keep_a_view_selected(self):
        if not self.sidebar.selectedItems() and self.sidebar.currentItem() is not None:
            self.sidebar.currentItem().setSelected(True)

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

        # One splitter slot, one pane per view, swapped by the switcher
        self.detail_panes = QStackedWidget()
        self.detail_panes.addWidget(self.details_pane)
        self.detail_panes.addWidget(self.notes_page.details_pane)
        row.addWidget(self.detail_panes, 1)

        self.details_container.setMinimumWidth(self.DETAILS_PANE_MIN_WIDTH)
        return self.details_container

    def current_details_pane(self):
        return self.detail_panes.currentWidget()

    # -- settings ---------------------------------------------------------

    def _restore_settings(self):
        view = self.settings.value(LIBRARY_VIEW_KEY, LIBRARY_VIEW_DEFAULT, type=str)
        if view not in LIBRARY_VIEWS:
            view = LIBRARY_VIEW_DEFAULT
        # Before the sidebar's signal is connected, so restoring writes nothing back
        self.sidebar.setCurrentRow(LIBRARY_VIEWS.index(view))
        self._apply_view(view)

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

    # -- the sidebar ------------------------------------------------------

    def current_view(self):
        row = self.sidebar.currentRow()
        return LIBRARY_VIEWS[row] if 0 <= row < len(LIBRARY_VIEWS) else LIBRARY_VIEW_DEFAULT

    def show_view(self, view):
        if view in LIBRARY_VIEWS:
            self.sidebar.setCurrentRow(LIBRARY_VIEWS.index(view))

    def on_view_changed(self, _row):
        view = self.current_view()
        self._apply_view(view)
        self.settings.setValue(LIBRARY_VIEW_KEY, view)

    def _apply_view(self, view):
        notes = view == LIBRARY_VIEW_NOTES
        self.pages.setCurrentIndex(LIBRARY_VIEWS.index(view))
        self.detail_panes.setCurrentIndex(LIBRARY_VIEWS.index(view))

        # Sort, cover size and Open Deck are the deck grid's; the notes list is by date
        self.sort_combo.setVisible(not notes)
        self.density_combo.setVisible(not notes)
        self.open_deck_button.setVisible(not notes)
        self.search_field.setPlaceholderText(
            notes_text("search_placeholder") if notes else SEARCH_DECKS_PLACEHOLDER
        )

        # Each view searches its own content, so the field starts clean on a switch
        self.search_field.clear()
        self._sync_details_toggle()

    # -- slots ------------------------------------------------------------

    def on_search_changed(self, text):
        if self.current_view() == LIBRARY_VIEW_NOTES:
            self.notes_page.set_search(text)
            return
        self.proxy_model.setFilterFixedString(text)
        self._update_empty_state()

    def on_card_activated(self, card_id):
        """Open the card view for a note's card, on its Notes tab."""
        deck = deck_manager.get_reference_deck()
        card = deck.get_card_by_id(card_id) if deck else None
        if card is None:
            return

        main_window = self.window()
        if hasattr(main_window, "open_card_view_tab"):
            main_window.open_card_view_tab(card, deck, show_notes=True)

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
        # The keyboard path
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
        if want and self.current_details_pane().details() is None:
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
        notes = self.current_view() == LIBRARY_VIEW_NOTES
        # Disabled until there's something to show, so the pane never opens empty
        self.details_toggle.setEnabled(self.current_details_pane().details() is not None)
        self.details_toggle.setChecked(is_open)
        if is_open:
            self.details_toggle.setIcon(QIcon.fromTheme("sidebar-collapse-right"))
            tooltip = notes_text("details_toggle_hide") if notes else "Hide deck details (Ctrl+I)"
        else:
            self.details_toggle.setIcon(QIcon.fromTheme("sidebar-expand-right"))
            tooltip = notes_text("details_toggle_show") if notes else "Show deck details (Ctrl+I)"
        self.details_toggle.setToolTip(tooltip)

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

        tab_widget.setTabIcon(index, QIcon.fromTheme("view-list-icons"))


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
