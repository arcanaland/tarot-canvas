from contextlib import contextmanager
from importlib.resources import files

from PyQt6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
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
    LIBRARY_DETAILS_BELOW_SHARE_DEFAULT,
    LIBRARY_DETAILS_BELOW_SHARE_KEY,
    LIBRARY_DETAILS_PANE_DEFAULT,
    LIBRARY_DETAILS_PANE_KEY,
    LIBRARY_SORT_DEFAULT,
    LIBRARY_SORT_KEY,
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_DEFAULT,
    LIBRARY_VIEW_ESOTERICA,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEWS,
    get_settings,
    record_deck_opened,
)
from tarot_canvas.ui import commands
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.commands import Scope, set_tooltip_with_keys
from tarot_canvas.ui.esoterica_text import label_for as esoterica_text
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
from tarot_canvas.ui.library.deselect import deselect_on_empty_click_or_escape
from tarot_canvas.ui.library.esoterica_page import EsotericaPage
from tarot_canvas.ui.library.notes_page import NotesPage
from tarot_canvas.ui.notes_text import text as notes_text
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets.placeholder_message import tinted_icon
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.widgets.search_field import search_field
from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider

# The deck view's name. The notes and esoterica views take theirs from notes_text and
# esoterica_text, which is where every string those views add belongs.
DECKS_VIEW_NAME = "Decks"
SEARCH_DECKS_PLACEHOLDER = "Search decks…"

ESOTERICA_VIEW_ICON = files("tarot_canvas.resources.icons").joinpath("esoterica.svg")

SORT_CHOICES = [
    ("Name", SORT_NAME),
    ("Author", SORT_AUTHOR),
    ("Card count", SORT_COUNT),
    ("Recently opened", SORT_RECENT),
]


class LibraryTab(BaseTab):
    deck_selected = pyqtSignal(object)  # Signal when a deck is selected

    DETAILS_PANE_MIN_WIDTH = 16 * units.GRID_UNIT
    DETAILS_PANE_SHARE = 0.3  # of the tab's width, the first time it opens beside
    DETAILS_PANE_MIN_HEIGHT = 8 * units.GRID_UNIT
    # A saved share outside this is a dragged-shut pane or a bad value, not a choice to keep
    DETAILS_PANE_BELOW_SHARES = (0.1, 0.9)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        # Whether selection opens the details pane: False once the user has closed it
        self._details_wanted = self.settings.value(
            LIBRARY_DETAILS_PANE_KEY, LIBRARY_DETAILS_PANE_DEFAULT, type=bool
        )
        # Beside, a width for the session, as the card view keeps its own. Below, a share of
        # the height, saved, so the reading pane is the size it was left at a window ago
        self._details_width = 0
        # Open when a switch landed on a view with nothing to show, so the pane closed for that
        # alone: the next view with something reopens it
        self._details_held = False
        self._below_share = self._saved_below_share()
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
        self.notes_page.note_activated.connect(self.on_note_activated)
        self.notes_page.details_changed.connect(self._sync_details_toggle)

        self.esoterica_page = EsotericaPage(deck=deck_manager.get_reference_deck())
        self.esoterica_page.card_activated.connect(self.on_esoterica_card_activated)
        self.esoterica_page.details_changed.connect(self._sync_details_toggle)
        self.esoterica_page.details_requested.connect(self._open_esoterica_details)

        # Every view but the deck grid is a list, with its pane below it
        self.list_pages = {
            LIBRARY_VIEW_NOTES: self.notes_page,
            LIBRARY_VIEW_ESOTERICA: self.esoterica_page,
        }

        # One page per sidebar row, in LIBRARY_VIEWS order
        self.pages = QStackedWidget()
        for view in LIBRARY_VIEWS:
            self.pages.addWidget(self.list_pages.get(view, grid))

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.pages)
        self.splitter.addWidget(self._build_details())
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        # The grid takes a window's growth; the pane keeps the width it was given
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._keep_details_extent)
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
        self.zoom_slider.zoom_on_ctrl_wheel(self.view.viewport())
        content_column.addLayout(below_header, 1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(content, 1)
        self.layout.addLayout(body, 1)

        # The sidebar first, so Tab goes from choosing a view to searching it
        QWidget.setTabOrder(self.sidebar, self.search_field)

        commands.bind(self, Scope.LIBRARY, {"library.toggle_details": self.details_toggle.click})

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

        self.search_field = search_field(SEARCH_DECKS_PLACEHOLDER)
        self.search_field.textChanged.connect(self.on_search_changed)
        row.addWidget(self.search_field, 1)

        self.sort_combo = QComboBox()
        for label, key in SORT_CHOICES:
            self.sort_combo.addItem(label, key)
        self.sort_combo.setToolTip("Sort decks")
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
        row.addWidget(self.sort_combo)

        self.zoom_slider = ZoomSlider(units.DENSITIES, "Cover size", LIBRARY_DENSITY_DEFAULT)
        self.zoom_slider.key_changed.connect(self.on_density_changed)
        row.addWidget(self.zoom_slider)

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
        """(icon, name, view) per sidebar row, in LIBRARY_VIEWS order"""
        return [
            (QIcon.fromTheme("view-list-icons"), DECKS_VIEW_NAME, LIBRARY_VIEW_DECKS),
            (QIcon.fromTheme("story-editor"), notes_text("view_name"), LIBRARY_VIEW_NOTES),
            # The app's own file, not a theme name
            (
                tinted_icon(ESOTERICA_VIEW_ICON),
                esoterica_text("library.view_name"),
                LIBRARY_VIEW_ESOTERICA,
            ),
        ]

    def _build_sidebar(self):
        """One row per view"""
        self.sidebar = PlacesSidebar(self._view_rows())
        self.sidebar.center_first_row_on(self.header.sizeHint().height())
        return self.sidebar

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
        activate_on_return(self.view)
        self.view.clicked.connect(self.on_deck_clicked)
        self.view.selectionModel().currentChanged.connect(self.on_current_changed)
        self.proxy_model.modelReset.connect(self._update_empty_state)
        self.proxy_model.rowsInserted.connect(self._update_empty_state)
        self.proxy_model.rowsRemoved.connect(self._update_empty_state)

        # The source's, not the proxy's, so a row the search hides still updates the pane
        self.model.dataChanged.connect(self._on_rows_changed)
        self.model.modelReset.connect(self._follow_shown_deck)

        # The pane keeps showing the deck it showed
        deselect_on_empty_click_or_escape(self.view)

        return self.view

    def _build_details(self):
        self.details_container = QWidget()
        # Left to right beside the page, top to bottom below it
        self._details_row = row = QBoxLayout(
            QBoxLayout.Direction.LeftToRight, self.details_container
        )
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # A line for the splitter handle to sit on, as the card view draws it
        self._details_seam = seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)
        row.addWidget(seam)

        self.details_pane = DeckDetailsPane()
        self.details_pane.open_requested.connect(self.on_deck_selected)
        self.details_pane.download_requested.connect(self._start_download)
        self.details_pane.cancel_requested.connect(self._cancel_download)

        # One splitter slot, one pane per view, swapped by the switcher
        self.detail_panes = QStackedWidget()
        for view in LIBRARY_VIEWS:
            page = self.list_pages.get(view)
            self.detail_panes.addWidget(self.details_pane if page is None else page.details_pane)
        row.addWidget(self.detail_panes, 1)

        self.details_container.setMinimumWidth(self.DETAILS_PANE_MIN_WIDTH)
        return self.details_container

    def current_details_pane(self):
        return self.detail_panes.currentWidget()

    def current_list_page(self):
        """The current view's page, or None for the deck grid"""
        return self.list_pages.get(self.current_view())

    # -- settings ---------------------------------------------------------

    def _restore_settings(self):
        view = self.settings.value(LIBRARY_VIEW_KEY, LIBRARY_VIEW_DEFAULT, type=str)
        if view not in LIBRARY_VIEWS:
            view = LIBRARY_VIEW_DEFAULT
        # Before the sidebar's signal is connected, so restoring writes nothing back
        self.sidebar.setCurrentRow(LIBRARY_VIEWS.index(view))
        self._apply_view(view)

        density = self.settings.value(LIBRARY_DENSITY_KEY, LIBRARY_DENSITY_DEFAULT, type=str)
        self.zoom_slider.set_key(density if density in units.DENSITIES else units.DENSITY_MEDIUM)

        sort_key = self.settings.value(LIBRARY_SORT_KEY, LIBRARY_SORT_DEFAULT, type=str)
        index = self.sort_combo.findData(sort_key)
        self.sort_combo.setCurrentIndex(index if index >= 0 else 0)

        # setCurrentIndex only emits when the index actually moves, so apply
        # both explicitly rather than relying on the signals above.
        self._apply_density(self.zoom_slider.key())
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
        page = self.list_pages.get(view)
        decks = page is None
        was_open = self.details_pane_is_open() or self._details_held
        self.pages.setCurrentIndex(LIBRARY_VIEWS.index(view))
        self.detail_panes.setCurrentIndex(LIBRARY_VIEWS.index(view))
        # One pane slot serves every view, so an open pane must not carry over to a view with
        # nothing selected, where it would open empty
        has_details = self.current_details_pane().details() is not None
        self._details_held = was_open and not has_details
        if not has_details:
            # Before the turn, so the extent kept is the one this pane had in its own view
            self._set_details_open(False)
        self._orient_details(Qt.Orientation.Horizontal if decks else Qt.Orientation.Vertical)
        if was_open and has_details:
            self._set_details_open(True)

        self.sort_combo.setVisible(decks)
        self.zoom_slider.setVisible(decks)
        self.open_deck_button.setVisible(decks)
        self.search_field.setPlaceholderText(
            SEARCH_DECKS_PLACEHOLDER if decks else page.search_placeholder()
        )

        # Each view searches its own content, so the field starts clean on a switch
        self.search_field.clear()
        self._sync_details_toggle()

    # -- slots ------------------------------------------------------------

    def can_find(self):
        return True

    def find(self):
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def on_search_changed(self, text):
        page = self.current_list_page()
        if page is not None:
            page.set_search(text)
            return
        self.proxy_model.setFilterFixedString(text)
        self._update_empty_state()

    def on_card_activated(self, card_id):
        """Open the card view for a note's card, on its Notes tab."""
        return self._open_card_view(card_id, show_notes=True)

    def on_esoterica_card_activated(self, card_id):
        """Open the card view for a source's covered card, on its Esoterica tab."""
        card_tab = self._open_card_view(card_id)
        if card_tab is not None:
            card_tab.show_esoterica_tab()

    def _open_card_view(self, card_id, show_notes=False):
        deck = deck_manager.get_reference_deck()
        card = deck.get_card_by_id(card_id) if deck else None
        if card is None:
            return None

        main_window = self.window()
        if hasattr(main_window, "open_card_view_tab"):
            return main_window.open_card_view_tab(card, deck, show_notes=show_notes)
        return None

    def on_note_activated(self, card_id, path):
        """Open the card view on one note."""
        card_tab = self.on_card_activated(card_id)
        if card_tab is not None:
            card_tab.open_note(path)

    def on_sort_changed(self):
        key = self.sort_combo.currentData()
        self.proxy_model.set_sort_key(key)
        self.settings.setValue(LIBRARY_SORT_KEY, key)

    def on_density_changed(self, density):
        self._apply_density(density)
        self.settings.setValue(LIBRARY_DENSITY_KEY, density)
        self.zoom_state_changed()

    # -- zoom ---------------------------------------------------------------

    def can_zoom(self, how):
        return self.zoom_slider.isVisibleTo(self) and self.zoom_slider.can_zoom(how)

    def zoom(self, how):
        self.zoom_slider.zoom(how)

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

    def _open_esoterica_details(self):
        self._set_details_open(True)

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
        self._details_held = False
        self.settings.setValue(LIBRARY_DETAILS_PANE_KEY, want)
        self._set_details_open(want)

    def _open_details_for_selection(self):
        if self._details_wanted:
            self._set_details_open(True)

    def _set_details_open(self, want):
        if want != self.details_pane_is_open():
            if want:
                self.details_container.show()
                self._size_details()
            else:
                self._keep_details_extent()
                self.details_container.hide()
        self._sync_details_toggle()

    def details_pane_is_below(self):
        return self.splitter.orientation() == Qt.Orientation.Vertical

    def _orient_details(self, orientation):
        """Put the pane beside the page or below it, each at the size it last had"""
        if orientation == self.splitter.orientation():
            return
        is_open = self.details_pane_is_open()
        if is_open:
            self._keep_details_extent()
        self.splitter.setOrientation(orientation)
        below = self.details_pane_is_below()
        self._details_row.setDirection(
            QBoxLayout.Direction.TopToBottom if below else QBoxLayout.Direction.LeftToRight
        )
        self._details_seam.setFrameShape(QFrame.Shape.HLine if below else QFrame.Shape.VLine)
        # Below, the list and the pane share a window's growth; beside, the grid takes it all
        self.splitter.setStretchFactor(1, 1 if below else 0)
        if below:
            self.details_container.setMinimumSize(0, self.DETAILS_PANE_MIN_HEIGHT)
        else:
            self.details_container.setMinimumSize(self.DETAILS_PANE_MIN_WIDTH, 0)
        if is_open:
            self._size_details()

    def _keep_details_extent(self, *_moved):
        """Remember the open pane's size: its width beside, its share of the height below"""
        if not self.details_pane_is_open():
            return
        page, pane = self.splitter.sizes()
        if not pane:
            return
        if not self.details_pane_is_below():
            self._details_width = pane
            return
        share = pane / (page + pane)
        low, high = self.DETAILS_PANE_BELOW_SHARES
        if low <= share <= high and share != self._below_share:
            self._below_share = share
            self.settings.setValue(LIBRARY_DETAILS_BELOW_SHARE_KEY, share)

    def _saved_below_share(self):
        try:
            share = self.settings.value(
                LIBRARY_DETAILS_BELOW_SHARE_KEY, LIBRARY_DETAILS_BELOW_SHARE_DEFAULT, type=float
            )
        except TypeError:  # a value that isn't a number at all
            return LIBRARY_DETAILS_BELOW_SHARE_DEFAULT
        low, high = self.DETAILS_PANE_BELOW_SHARES
        return share if low <= share <= high else LIBRARY_DETAILS_BELOW_SHARE_DEFAULT

    def _size_details(self):
        """Give the open pane its remembered size, or its share of the tab the first time"""
        below = self.details_pane_is_below()
        total = (self.splitter.height() if below else self.splitter.width()) - (
            self.splitter.handleWidth()
        )
        if below:
            extent = round(total * self._below_share)
        else:
            extent = self._details_width or round(total * self.DETAILS_PANE_SHARE)
        self.splitter.setSizes([max(0, total - extent), extent])

    def _sync_details_toggle(self):
        """Keep the toggle saying what the next press will do"""
        is_open = self.details_pane_is_open()
        # Disabled until there's something to show, so the pane never opens empty
        self.details_toggle.setEnabled(self.current_details_pane().details() is not None)
        self.details_toggle.setChecked(is_open)
        if self.details_pane_is_below():
            # Breeze has no bottom-panel pair, so the checked state says whether it's open
            icon = "view-split-top-bottom"
        else:
            icon = "sidebar-collapse-right" if is_open else "sidebar-expand-right"
        self.details_toggle.setIcon(QIcon.fromTheme(icon))
        page = self.current_list_page()
        if page is not None:
            tooltip = page.details_toggle_tooltip(is_open)
        elif is_open:
            tooltip = "Hide deck details"
        else:
            tooltip = "Show deck details"
        set_tooltip_with_keys(self.details_toggle, tooltip, "library.toggle_details")

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
