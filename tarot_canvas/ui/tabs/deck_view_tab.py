from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets.card_thumbnail import CardThumbnail
from tarot_canvas.ui.widgets.deck_header import DeckHeader

SECTION_TITLE_SCALE = 1.15


class CardScrollArea(QScrollArea):
    """Custom scroll area that scrolls horizontally, not vertically"""

    def __init__(self, height, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Set fixed height to ensure all cards are fully visible
        self.setFixedHeight(height)


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
        self.card_size = QSize(150, 240)
        # Calculate row height (card height + padding + scrollbar)
        self.row_height = self.card_size.height() + 40  # Extra padding for larger cards
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

        # Main content widget with vertical layout
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(15)

        # Deck-level header, inline at the top of the page (not a modal dialog)
        self.header = DeckHeader(self.deck, parent=content)
        main_layout.addWidget(self.header)

        self.add_major_arcana_journey(main_layout)

        # Add Minor Arcana sections
        self.add_minor_arcana_sections(main_layout)

        # The card rows have a fixed height, so without this the scroll area's slack
        # lands on the section titles and pushes them off their rows.
        main_layout.addStretch()

        # Add the content to a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        self.layout.addWidget(scroll)

    def section_title(self, text):
        """A section heading in the system font, scaled rather than hardcoded."""
        label = QLabel(text)
        label.setFont(units.scaled_font(QApplication.font(), SECTION_TITLE_SCALE, bold=True))
        return label

    def add_major_arcana_journey(self, layout):
        """Add the Major Arcana journey section"""
        layout.addWidget(self.section_title("Major Arcana"))

        # Get Major Arcana cards
        major_arcana = self.deck.get_cards_by_type("major_arcana")
        # Sort by number
        major_arcana.sort(key=lambda card: card.get("number", 999))

        # Create scroll area for the cards with fixed height
        scroll = CardScrollArea(self.row_height)
        content = QWidget()
        journey_layout = QHBoxLayout(content)
        journey_layout.setSpacing(5)
        journey_layout.setContentsMargins(5, 5, 5, 5)

        # Add cards to journey
        for card in major_arcana:
            thumbnail = CardThumbnail(card, self.deck.deck_path, size=self.card_size)
            # Connect signals to our local handlers
            thumbnail.clicked.connect(lambda c=card: self.handle_card_click(c))
            thumbnail.double_clicked.connect(lambda c=card: self.handle_card_double_click(c))
            journey_layout.addWidget(thumbnail)

        # Add spacer to prevent cards from stretching
        journey_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def add_minor_arcana_sections(self, layout):
        """Add sections for each Minor Arcana suit"""
        # Get all suits
        suits = self.deck.get_suits()

        # Check if we have any suits at all
        if not suits:
            # Add a note about excluded cards if there's a reason
            exclusion_reason = self.deck.get_exclusion_reason()
            if exclusion_reason:
                note_label = QLabel(f"Note: {exclusion_reason}")
                note_label.setWordWrap(True)
                note_font = QApplication.font()
                note_font.setItalic(True)
                note_label.setFont(note_font)
                note_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
                layout.addWidget(note_label)

        for suit in suits:
            # Get cards for this suit
            suit_cards = self.deck.get_cards_by_suit(suit)

            if not suit_cards:
                continue

            # Get display name for the suit
            display_suit = self.deck.get_display_suit_name(suit)

            layout.addWidget(self.section_title(display_suit))

            # Sort cards by rank (numeric order for numbered cards, then court cards)
            rank_order = {
                "ace": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
                "nine": 9,
                "ten": 10,
                "page": 11,
                "knight": 12,
                "queen": 13,
                "king": 14,
            }
            suit_cards.sort(key=lambda card: rank_order.get(card.get("rank"), 999))

            # Create scroll area for the cards with fixed height
            scroll = CardScrollArea(self.row_height)
            content = QWidget()
            cards_layout = QHBoxLayout(content)
            cards_layout.setSpacing(5)
            cards_layout.setContentsMargins(5, 5, 5, 5)

            # Add cards to row
            for card in suit_cards:
                thumbnail = CardThumbnail(card, self.deck.deck_path, size=self.card_size)
                # Connect signals to our local handlers
                thumbnail.clicked.connect(lambda c=card: self.handle_card_click(c))
                thumbnail.double_clicked.connect(lambda c=card: self.handle_card_double_click(c))
                cards_layout.addWidget(thumbnail)

            # Add spacer to prevent cards from stretching
            cards_layout.addStretch()

            scroll.setWidget(content)
            layout.addWidget(scroll)

    def handle_card_click(self, card):
        """Handle single click on a card thumbnail"""
        if card.get("image"):
            self.card_clicked.emit(card.get("image"))

    def handle_card_double_click(self, card):
        """Handle double click on a card thumbnail"""
        # Emit signal to request opening card view
        self.card_action_requested.emit("double_click", card, self.deck)

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
                    # Create and set the cards-stack icon from theme or fallback
                    icon = QIcon.fromTheme(
                        "view-grid",
                        QIcon(
                            str(
                                Path(__file__).parent.parent.parent
                                / "resources"
                                / "icons"
                                / "cards-stack.png"
                            )
                        ),
                    )
                    tab_widget.setTabIcon(index, icon)
