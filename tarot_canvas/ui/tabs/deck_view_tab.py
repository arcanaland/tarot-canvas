from PyQt6.QtCore import QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.settings import DECK_VIEW_DENSITY_DEFAULT, DECK_VIEW_DENSITY_KEY, get_settings
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.card_transfer import copy_cards_to_clipboard
from tarot_canvas.ui.deck_view.card_delegate import CardDelegate
from tarot_canvas.ui.deck_view.card_model import CardFilter, CardModel, CardRole
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets import deck_header
from tarot_canvas.ui.widgets.deck_header import DeckHeader
from tarot_canvas.ui.widgets.search_field import search_field
from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider

SECTION_MARGIN = deck_header.EDGE_MARGIN
FIND_CARD_PLACEHOLDER = "Find card…"


class DeckViewTab(BaseTab):
    card_clicked = pyqtSignal(str)  # Signal when a card is clicked
    card_action_requested = pyqtSignal(
        str, dict, object
    )  # Signal for card actions (action, card, deck)
    title_changed = pyqtSignal(str)  # Signal to update the tab title

    def __init__(self, deck_path=None, parent=None):
        super().__init__(parent)
        self.deck_path = deck_path
        self.deck = None
        self.settings = get_settings()
        self.setup_ui()

        # Set the tab icon after a short delay to ensure the tab is added
        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        if self.deck_path:
            # Load deck from deck_path
            self.load_deck(self.deck_path)
        else:
            self.set_placeholder("Open a deck to view its cards")

    def load_deck(self, deck_path):
        self.clear_layout()

        # Load the deck
        self.deck = TarotDeck(deck_path)

        # Get the parent tab widget to update its title directly
        parent_tab_widget = None
        parent = self.parent()
        while parent:
            if isinstance(parent, QTabWidget):
                parent_tab_widget = parent
                break
            parent = parent.parent()

        # Directly update the tab title if we can find the parent tab widget
        if parent_tab_widget:
            tab_index = parent_tab_widget.indexOf(self)
            if tab_index != -1:
                parent_tab_widget.setTabText(tab_index, self.deck.get_name())
                print(f"Direct title update: {self.deck.get_name()}")

        # Also emit the signal as a backup mechanism
        self.title_changed.emit(self.deck.get_name())

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Pinned above the page, as the Library's is
        self.layout.addWidget(self._build_header())

        # Main content widget with vertical layout
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Deck-level header at the top of the page
        self.header = DeckHeader(self.deck, parent=content)
        main_layout.addWidget(self.header)

        # The grid's own spacing makes up the rest of the margin, so headings line up
        # with the header's text
        grid_row = QVBoxLayout()
        self.grid = self._build_grid()
        inset = SECTION_MARGIN - self.grid.spacing()
        grid_row.setContentsMargins(inset, 0, inset, SECTION_MARGIN)
        grid_row.addWidget(self.grid)
        main_layout.addLayout(grid_row)
        main_layout.addStretch()

        # Add the content to a scroll area
        self.scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        # Anywhere on the page, where a wheel over the grid ends up too
        self.zoom_slider.zoom_on_ctrl_wheel(scroll.viewport())

        # The frame would put a line between the banner and the tab bar.
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.layout.addWidget(scroll)

    def _build_header(self):
        header = QWidget()
        row = QHBoxLayout(header)
        # Level with the banner's text and the headings
        row.setContentsMargins(
            SECTION_MARGIN, units.LARGE_SPACING, SECTION_MARGIN, units.LARGE_SPACING
        )
        row.setSpacing(units.LARGE_SPACING)

        self.search_field = search_field(FIND_CARD_PLACEHOLDER)
        self.search_field.textChanged.connect(self.on_search_changed)
        row.addWidget(self.search_field, 1)

        self.zoom_slider = ZoomSlider(units.DENSITIES, "Cover size", DECK_VIEW_DENSITY_DEFAULT)
        density = self.settings.value(DECK_VIEW_DENSITY_KEY, DECK_VIEW_DENSITY_DEFAULT, type=str)
        self.zoom_slider.set_key(
            density if density in units.DENSITIES else DECK_VIEW_DENSITY_DEFAULT
        )
        self.zoom_slider.key_changed.connect(self.on_density_changed)
        row.addWidget(self.zoom_slider)
        return header

    def _build_grid(self):
        self.model = CardModel(self.deck, self)
        # The grid shows what Find leaves of the deck
        self.found = CardFilter(self)
        self.found.setSourceModel(self.model)
        grid = SectionsView()
        grid.setModel(self.found)
        self.delegate = CardDelegate(grid, density=self.zoom_slider.key())
        grid.setItemDelegate(self.delegate)

        grid.activated.connect(self.on_card_activated)
        activate_on_return(grid)
        grid.clicked.connect(self.on_card_clicked)
        grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        grid.customContextMenuRequested.connect(self.on_context_menu)
        grid.selectionModel().currentChanged.connect(self.on_current_changed)
        grid.selectionModel().selectionChanged.connect(self.edit_state_changed)
        return grid

    # -- cards ------------------------------------------------------------

    def selected_cards(self):
        """The selected cards, in deck order"""
        indexes = sorted(self.grid.selectionModel().selectedIndexes(), key=lambda i: i.row())
        return [index.data(CardRole) for index in indexes]

    def on_card_clicked(self, index):
        card = index.data(CardRole)
        if card and card.get("image"):
            self.card_clicked.emit(card.get("image"))

    def on_card_activated(self, index):
        card = index.data(CardRole)
        if card:
            self.card_action_requested.emit("double_click", card, self.deck)

    def on_current_changed(self, current, _previous):
        """Keep the keyboard's card on screen; the page scrolls, not the grid"""
        if not current.isValid():
            return
        rect = self.grid.visualRect(current)
        centre = self.grid.viewport().mapTo(self.scroll.widget(), rect.center())
        margin = self.grid.spacing()
        self.scroll.ensureVisible(
            centre.x(), centre.y(), rect.width() // 2 + margin, rect.height() // 2 + margin
        )

    def card_menu(self, index):
        """Open opens the card under the pointer; Copy copies the selection"""
        menu = QMenu(self)
        open_action = menu.addAction(QIcon.fromTheme("document-open"), "&Open Card")
        open_action.triggered.connect(lambda: self.on_card_activated(index))
        copy_action = menu.addAction(QIcon.fromTheme("edit-copy"), "&Copy Card")
        copy_action.triggered.connect(self.copy_card)
        return menu

    def on_context_menu(self, pos):
        index = self.grid.indexAt(pos)
        if not index.isValid() or index.data(CardRole) is None:
            return
        selection = self.grid.selectionModel()
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        menu = self.card_menu(index)
        menu.exec(self.grid.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def on_density_changed(self, density):
        self.settings.setValue(DECK_VIEW_DENSITY_KEY, density)
        if self.delegate.set_density(density):
            self.grid.doItemsLayout()
        self.zoom_state_changed()

    # -- find ---------------------------------------------------------------

    def can_find(self):
        return self.deck is not None

    def find(self):
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def on_search_changed(self, text):
        self.found.setFilterFixedString(text)
        self.edit_state_changed()

    # -- zoom ---------------------------------------------------------------
    # View > Zoom, Ctrl+wheel and the slider are one control: the cover size

    def can_zoom(self, how):
        return self.deck is not None and self.zoom_slider.can_zoom(how)

    def zoom(self, how):
        self.zoom_slider.zoom(how)

    # -- edit ---------------------------------------------------------------

    def can_copy_card(self):
        return self.deck is not None and self.grid.selectionModel().hasSelection()

    def copy_card(self):
        cards = self.selected_cards()
        if cards:
            copy_cards_to_clipboard(cards, self.deck)

    def clear_layout(self):
        """Clear the current layout"""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def update_tab_icon(self):
        """Update the tab with a deck icon"""
        parent = self.parent()
        if parent:
            # Find the tab widget that contains this widget
            tab_widget = None
            parent_widget = parent

            # Try to find a parent that has setTabIcon method
            while parent_widget and not tab_widget:
                if hasattr(parent_widget, "setTabIcon"):
                    tab_widget = parent_widget
                    break
                parent_widget = parent_widget.parent()

            # If we found a tab widget, update the tab icon
            if tab_widget:
                index = tab_widget.indexOf(self)
                if index >= 0:
                    tab_widget.setTabIcon(index, QIcon.fromTheme("view-grid"))
