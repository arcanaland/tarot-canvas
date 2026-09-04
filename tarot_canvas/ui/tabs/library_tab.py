from pathlib import Path

from PyQt6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QToolButton,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    LIBRARY_DENSITY_DEFAULT,
    LIBRARY_DENSITY_KEY,
    LIBRARY_SORT_DEFAULT,
    LIBRARY_SORT_KEY,
    get_settings,
    record_deck_opened,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_delegate import DeckDelegate
from tarot_canvas.ui.library.deck_model import (
    SORT_AUTHOR,
    SORT_COUNT,
    SORT_NAME,
    SORT_RECENT,
    DeckFilterProxyModel,
    DeckListModel,
    DeckRole,
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.setup_ui()

        # Set the tab icon after a short delay to ensure the tab is added
        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.model = DeckListModel(deck_manager.get_all_decks(), parent=self)
        self.proxy_model = DeckFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        self.layout.addWidget(self._build_header())
        self.layout.addWidget(self._build_view())
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)
        self.layout.addWidget(self.empty_label)

        self._restore_settings()
        self._update_empty_state()

    def _build_header(self):
        """The HIG puts add-content controls on a header above the view, not
        on a button floating in dead space below it."""
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
        # No frame anywhere: the cover art is self-delimiting, and the HIG asks
        # for no unnecessary frames around content views.
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # `activated` fires on whichever gesture the user's system setting says
        # opens an item, so single- vs double-click follows the desktop for free.
        self.view.activated.connect(self.on_deck_activated)
        self.view.selectionModel().currentChanged.connect(self.on_current_changed)
        self.proxy_model.modelReset.connect(self._update_empty_state)
        self.proxy_model.rowsInserted.connect(self._update_empty_state)
        self.proxy_model.rowsRemoved.connect(self._update_empty_state)

        return self.view

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
        deck = current.data(DeckRole) if current.isValid() else None
        if deck is not None:
            self.deck_selected.emit(deck)

    def on_deck_activated(self, index):
        deck = index.data(DeckRole)
        if deck is not None:
            self.on_deck_selected(deck)

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

    def refresh(self):
        """Reload the deck list, keeping the selected deck selected if it survives."""
        selected = self.current_deck()
        self.model.set_decks(deck_manager.get_all_decks())
        self.proxy_model.refresh_recent()
        if selected is not None:
            self.select_deck_path(selected.deck_path)
        self._update_empty_state()

    def current_deck(self):
        index = self.view.currentIndex()
        return index.data(DeckRole) if index.isValid() else None

    def select_deck_path(self, deck_path):
        for row in range(self.proxy_model.rowCount()):
            index = self.proxy_model.index(row, 0)
            deck = index.data(DeckRole)
            if deck is not None and deck.deck_path == deck_path:
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
