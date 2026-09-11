import os

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QIcon, QPixmap, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.card_transfer import CARD_MIME, card_mime_data, copy_card_to_clipboard


def card_row(index):
    """The row's {"type": "card", "card", "deck"} dict, or None for a group row"""
    data = index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None
    return data if data and data.get("type") == "card" else None


class CardTreeModel(QStandardItemModel):
    """Card rows drag as the card payload; group rows do not drag at all."""

    def mimeTypes(self):
        return [CARD_MIME]

    def mimeData(self, indexes):
        for index in indexes:
            row = card_row(index)
            if row:
                return card_mime_data(row["card"], row["deck"])
        return None

    def flags(self, index):
        flags = super().flags(index)
        if card_row(index):
            return flags | Qt.ItemFlag.ItemIsDragEnabled
        return flags & ~Qt.ItemFlag.ItemIsDragEnabled


class CardTreeView(QTreeView):
    """Shows the card's art under the pointer while it is dragged, not the text row."""

    DRAG_HEIGHT = 120

    def startDrag(self, supported_actions):
        indexes = [index for index in self.selectedIndexes() if card_row(index)]
        mime = self.model().mimeData(indexes) if indexes else None
        if mime is None:
            return

        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self.drag_pixmap(card_row(indexes[0])["card"])
        if pixmap is not None:
            drag.setPixmap(pixmap)
            size = pixmap.deviceIndependentSize()
            drag.setHotSpot(QPoint(round(size.width() / 2), round(size.height() / 2)))
        drag.exec(supported_actions, Qt.DropAction.CopyAction)

    def drag_pixmap(self, card):
        path = card.get("image")
        if not path or not os.path.exists(path):
            return None
        source = QPixmap(path)
        if source.isNull():
            return None
        dpr = self.devicePixelRatioF()
        pixmap = source.scaledToHeight(
            round(self.DRAG_HEIGHT * dpr), Qt.TransformationMode.SmoothTransformation
        )
        pixmap.setDevicePixelRatio(dpr)
        return pixmap


class CardExplorerPanel(QWidget):
    # Signal emitted when a card action is requested
    card_action_requested = pyqtSignal(str, dict, object)  # action, card, deck
    # Signal emitted when the header's close button is clicked
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_deck = None
        self.setup_ui()
        self.populate_deck_selector()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header label with a close button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        header = QLabel("Card Explorer")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        header_layout.addWidget(header, 1)

        self.close_button = QToolButton()
        self.close_button.setAutoRaise(True)
        close_icon = QIcon.fromTheme("window-close")
        if close_icon.isNull():
            self.close_button.setText("\N{MULTIPLICATION SIGN}")
        else:
            self.close_button.setIcon(close_icon)
        self.close_button.setToolTip("Hide Card Explorer (Ctrl+E)")
        self.close_button.setAccessibleName("Hide Card Explorer")
        self.close_button.clicked.connect(self.close_requested)
        header_layout.addWidget(self.close_button)

        layout.addLayout(header_layout)

        # Tree view for cards
        self.tree_view = CardTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(15)
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        # Card rows drag onto a canvas
        self.tree_view.setDragEnabled(True)
        self.tree_view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        # Connect signals
        self.tree_view.clicked.connect(self.on_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_card_menu)

        # Create model
        self.model = CardTreeModel()
        self.tree_view.setModel(self.model)

        layout.addWidget(self.tree_view, 1)  # 1 = stretch factor

        # Add a separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Create deck selector at the bottom
        deck_layout = QHBoxLayout()
        deck_layout.setContentsMargins(5, 5, 5, 5)

        self.deck_selector = QComboBox()
        self.deck_selector.currentIndexChanged.connect(self.on_deck_changed)
        self.deck_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.deck_selector.setMinimumContentsLength(10)
        deck_layout.addWidget(self.deck_selector, 1)  # 1 = stretch factor

        layout.addLayout(deck_layout)

        self.setMaximumWidth(300)

    def preferred_width(self):
        """Width at which the widest row in the card list fits without eliding."""
        tree = self.tree_view
        width = tree.sizeHintForColumn(0)
        width += 2 * tree.frameWidth()

        # the scrollbar is a permanent fixture
        width += tree.verticalScrollBar().sizeHint().width()
        margins = self.layout().contentsMargins()
        width += margins.left() + margins.right()

        return min(max(width, self.minimumSizeHint().width()), self.maximumWidth())

    def populate_deck_selector(self):
        """Fill the deck selector dropdown with available decks"""
        # Get all available decks
        self.available_decks = deck_manager.get_all_decks()

        # Add decks to combo box
        self.deck_selector.clear()
        for deck in self.available_decks:
            self.deck_selector.addItem(deck.get_name())

        # Select first deck by default if available
        if self.deck_selector.count() > 0:
            self.deck_selector.setCurrentIndex(0)
            self.on_deck_changed(0)

    def on_deck_changed(self, index):
        """Handle deck selection change"""
        if 0 <= index < len(self.available_decks):
            self.current_deck = self.available_decks[index]
            self.populate_tree()

    def populate_tree(self):
        """Populate the tree with cards from the selected deck"""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Cards"])

        if not self.current_deck:
            return

        # Create Major Arcana group
        major_group = QStandardItem("Major Arcana")
        major_group.setData(
            {"type": "group", "group": "major_arcana", "deck": self.current_deck},
            Qt.ItemDataRole.UserRole,
        )

        # Add Major Arcana cards
        major_cards = self.current_deck.get_cards_by_type("major_arcana")
        if major_cards:  # Only add if there are cards
            for card in major_cards:
                card_item = QStandardItem(card["name"])
                card_item.setData(
                    {"type": "card", "card": card, "deck": self.current_deck},
                    Qt.ItemDataRole.UserRole,
                )
                major_group.appendRow(card_item)

            self.model.appendRow(major_group)

        # Create suit groups
        suits = self.current_deck.get_suits()
        for suit in suits:
            # Skip entirely excluded suits
            if self.current_deck.is_suit_excluded(suit):
                continue

            # Get display name for suit (aliased if available)
            display_suit = self.current_deck.get_display_suit_name(suit)

            # Create group with display name
            suit_group = QStandardItem(display_suit)
            suit_group.setData(
                {"type": "group", "group": suit, "deck": self.current_deck},
                Qt.ItemDataRole.UserRole,
            )

            # Add cards for this suit
            suit_cards = self.current_deck.get_cards_by_suit(suit)
            if suit_cards:  # Only add if there are cards
                for card in suit_cards:
                    card_item = QStandardItem(card["name"])
                    card_item.setData(
                        {"type": "card", "card": card, "deck": self.current_deck},
                        Qt.ItemDataRole.UserRole,
                    )
                    suit_group.appendRow(card_item)

                self.model.appendRow(suit_group)

        # Expand all top-level items by default
        for i in range(self.model.rowCount()):
            index = self.model.index(i, 0)
            self.tree_view.expand(index)

    def on_item_clicked(self, index):
        """Handle single clicks - just select the item without taking action"""
        # Don't emit any signal - just let the tree view handle selection
        pass

    def on_item_double_clicked(self, index):
        """Handle double clicks with context-sensitive actions"""
        item = self.model.itemFromIndex(index)
        data = item.data(Qt.ItemDataRole.UserRole)

        if data and data["type"] == "card":
            # Emit the action signal - main window will decide what to do based on context
            self.card_action_requested.emit("double_click", data["card"], data["deck"])

    def card_menu(self, index):
        """Open and Copy for a card row; None for a group row or empty space"""
        row = card_row(index)
        if not row:
            return None
        card, deck = row["card"], row["deck"]

        menu = QMenu(self)
        open_action = menu.addAction(QIcon.fromTheme("document-open"), "&Open Card")
        open_action.triggered.connect(
            lambda: self.card_action_requested.emit("view_card", card, deck)
        )
        copy_action = menu.addAction(QIcon.fromTheme("edit-copy"), "&Copy Card")
        copy_action.triggered.connect(lambda: copy_card_to_clipboard(card, deck))
        return menu

    def show_card_menu(self, pos):
        menu = self.card_menu(self.tree_view.indexAt(pos))
        if menu is not None:
            menu.exec(self.tree_view.viewport().mapToGlobal(pos))
            menu.deleteLater()

    def refresh(self):
        """Refresh the deck selector and tree view"""
        # Store current selected deck name
        current_deck_name = self.deck_selector.currentText() if self.current_deck else None

        # Repopulate deck selector
        self.populate_deck_selector()

        # Try to restore previous selection
        if current_deck_name:
            index = self.deck_selector.findText(current_deck_name)
            if index >= 0:
                self.deck_selector.setCurrentIndex(index)
            else:
                # If previous deck is no longer available, select first deck
                self.deck_selector.setCurrentIndex(0) if self.deck_selector.count() > 0 else None
