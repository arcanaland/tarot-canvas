from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.card_search import CardTerms, Query
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.library.cover_cache import CoverCache

THUMBNAIL_SIZE = QSize(25, 40)

# Shared by every palette, so reopening one decodes nothing
_THUMBNAILS = CoverCache(capacity=128)


class CommandPaletteItem(QWidget):
    """Custom widget for command palette items with card image thumbnail"""

    def __init__(self, card, deck, device_pixel_ratio=1.0, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Card thumbnail, decoded at display size; left empty if there is no image
        icon_label = QLabel()
        icon_label.setFixedSize(THUMBNAIL_SIZE)
        pixmap = _THUMBNAILS.get(card.get("image"), THUMBNAIL_SIZE, device_pixel_ratio)
        if pixmap is not None:
            icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label)

        # Card information
        info_layout = QVBoxLayout()

        # Card name - primary text
        name_label = QLabel(card.get("name"))
        name_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(name_label)

        # Card details - secondary text
        card_type = card.get("type", "").replace("_", " ").title()
        if card.get("type") == "minor_arcana":
            suit = card.get("suit", "").title()
            rank = card.get("rank", "").title()
            details = f"{suit} {rank} - {deck.get_name()}"
        else:
            details = f"{card_type} - {deck.get_name()}"

        details_label = QLabel(details)
        details_label.setStyleSheet("color: gray; font-size: 10px;")
        info_layout.addWidget(details_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Action hint based on context (will be set later)
        self.action_label = QLabel("Open")
        self.action_label.setStyleSheet("color: #666; font-size: 10px;")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.action_label)

    def set_action_hint(self, text):
        """Update the action hint text"""
        self.action_label.setText(text)


class ResultItem(QListWidgetItem):
    """A result row that sorts by search tier, then by deck order"""

    def __init__(self, card, deck, position):
        super().__init__()
        self.terms = CardTerms(card, deck.get_name())
        self.position = position
        self.order = (False, 0, position)

    def __lt__(self, other):
        return self.order < other.order


class CommandPalette(QDialog):
    card_selected = pyqtSignal(dict, object)  # Card data, Deck

    def __init__(self, parent=None, active_tab_type=None):
        super().__init__(parent)
        self.setWindowTitle("Find Card")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        # Store active tab type to determine behavior
        self.active_tab_type = active_tab_type

        # Remove window decorations for a cleaner look
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)

        # Setup UI
        self.setup_ui()

        # Load all cards
        self.load_cards()

        # Connect escape key to close dialog
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.close)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for cards...")
        self.search_input.textChanged.connect(self.filter_results)
        layout.addWidget(self.search_input)

        # Context indicator
        action_text = "Add to Canvas" if self.active_tab_type == "canvas" else "Open Card View"
        context_label = QLabel(f"Press Enter to {action_text}")
        context_label.setStyleSheet("color: #666; font-style: italic;")
        context_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(context_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.itemActivated.connect(self.on_item_activated)
        layout.addWidget(self.results_list)

        # Set focus to search input
        self.search_input.setFocus()

    def load_cards(self):
        """Load cards from the reference deck only"""
        self.cards = []

        # Get the reference deck
        reference_deck = deck_manager.get_reference_deck()

        # Only load cards from the reference deck
        if reference_deck:
            for card in reference_deck._cards:
                self.cards.append((card, reference_deck))

        self.build_results()

    def build_results(self):
        """Build one row per card; filtering hides rows rather than rebuilding them"""
        window = self.parentWidget()
        device_pixel_ratio = window.devicePixelRatioF() if window else 1.0

        for position, (card, deck) in enumerate(self.cards):
            # Create list item
            item = ResultItem(card, deck, position)
            item.setSizeHint(QSize(0, 60))  # Set appropriate height

            # Create and add custom widget
            card_widget = CommandPaletteItem(card, deck, device_pixel_ratio)

            # Set action hint based on active tab type
            action_text = "Add to Canvas" if self.active_tab_type == "canvas" else "Open"
            card_widget.set_action_hint(action_text)

            # Store card and deck data with the item
            item.setData(Qt.ItemDataRole.UserRole, (card, deck))

            # Add to list
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, card_widget)

        self.select_first_visible()

    def visible_rows(self):
        return [
            row
            for row in range(self.results_list.count())
            if not self.results_list.isRowHidden(row)
        ]

    def select_first_visible(self):
        rows = self.visible_rows()
        self.results_list.setCurrentRow(rows[0] if rows else -1)

    def filter_results(self):
        """Hide the cards that don't match, and rank the rest best first"""
        query = Query(self.search_input.text())

        items = [self.results_list.item(row) for row in range(self.results_list.count())]
        for item in items:
            tier = item.terms.tier(query)
            # Misses sort last; they are hidden anyway
            item.order = (tier is None, tier or 0, item.position)

        # Sorting moves rows, and each row's widget moves with it
        self.results_list.sortItems()
        for item in items:
            item.setHidden(item.order[0])

        self.select_first_visible()

    def step_selection(self, step):
        """Move the selection by one visible row, wrapping at either end"""
        rows = self.visible_rows()
        if not rows:
            return
        current = self.results_list.currentRow()
        if current not in rows:
            self.results_list.setCurrentRow(rows[0])
            return
        self.results_list.setCurrentRow(rows[(rows.index(current) + step) % len(rows)])

    def on_item_activated(self, item):
        """Handle item activation (double-click or Enter key)"""
        card, deck = item.data(Qt.ItemDataRole.UserRole)

        # Emit signal with selected card and deck
        self.card_selected.emit(card, deck)

        # Close dialog
        self.accept()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # If an item is selected, activate it
            current_item = self.results_list.currentItem()
            if current_item and not current_item.isHidden():
                self.on_item_activated(current_item)
        elif event.key() == Qt.Key.Key_Up:
            # Handle up key when in search input
            if self.search_input.hasFocus() and self.visible_rows():
                self.step_selection(-1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Down:
            # Handle down key when in search input
            if self.search_input.hasFocus() and self.visible_rows():
                self.step_selection(1)
                event.accept()
                return

        # Pass unhandled events to parent
        super().keyPressEvent(event)
