from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import (
    QGridLayout, QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QFrame, QSizePolicy, QStackedWidget, QDialog, QTabWidget
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QFont, QColor, QPainter, QPen, QIcon
import os
from pathlib import Path
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.widgets.card_thumbnail import CardThumbnail

class CardScrollArea(QScrollArea):
    """Custom scroll area that scrolls horizontally, not vertically"""
    def __init__(self, height, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Set fixed height to ensure all cards are fully visible
        self.setFixedHeight(height)
        
class DeckInfoDialog(QDialog):
    """Dialog to display deck metadata"""
    def __init__(self, deck, parent=None):
        super().__init__(parent)
        self.deck = deck
        self.setWindowTitle(f"About {deck.get_name()}")
        self.setMinimumWidth(400)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Deck Title
        title_label = QLabel(self.deck.get_name())
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        creator_info = self.deck._metadata.get("deck", {}).get("author", "Unknown")
        creator_label = QLabel(f"Created by: {creator_info}")
        
        # Version
        version = self.deck.get_version()
        version_label = QLabel(f"Version: {version}")
        
        # Card count
        card_count = len(self.deck._cards)
        count_label = QLabel(f"Card count: {card_count}")
        
        # Description (if available)
        description = self.deck.get_description()
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        
        # Add widgets to layout
        layout.addWidget(title_label)
        layout.addWidget(creator_label)
        layout.addWidget(version_label)
        layout.addWidget(count_label)
        if description:
            layout.addWidget(QLabel(""))  # Spacer
            layout.addWidget(desc_label)
        layout.addStretch()
        layout.addWidget(close_button)

class DeckViewTab(BaseTab):
    card_clicked = pyqtSignal(str)  # Signal when a card is clicked
    card_action_requested = pyqtSignal(str, dict, object)  # Signal for card actions (action, card, deck)
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
        
        # Add the Major Arcana journey with deck info button
        self.add_major_arcana_journey(main_layout)
        
        # Add Minor Arcana sections
        self.add_minor_arcana_sections(main_layout)
        
        # Add the content to a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        
        self.layout.addWidget(scroll)
    
    def show_deck_info(self):
        """Show the deck information dialog"""
        dialog = DeckInfoDialog(self.deck, self)
        dialog.exec()
    
    def add_major_arcana_journey(self, layout):
        """Add the Major Arcana journey section"""
        # Create a header with section title and info button
        header_layout = QHBoxLayout()
        
        # Section title
        journey_title = QLabel("Major Arcana - The Fool's Journey")
        journey_title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        
        # Info button
        info_button = QPushButton("Deck Info")
        info_button.setMaximumWidth(100)
        info_button.clicked.connect(self.show_deck_info)
        
        header_layout.addWidget(journey_title)
        header_layout.addStretch()
        header_layout.addWidget(info_button)
        
        layout.addLayout(header_layout)
        
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
        
        for suit in suits:
            # Get cards for this suit
            suit_cards = self.deck.get_cards_by_suit(suit)
            
            if not suit_cards:
                continue
                
            # Get display name for the suit
            display_suit = self.deck.get_display_suit_name(suit)
            
            # Section title
            suit_title = QLabel(f"{display_suit}")
            suit_title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            layout.addWidget(suit_title)
            
            # Sort cards by rank (numeric order for numbered cards, then court cards)
            rank_order = {"ace": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, 
                          "seven": 7, "eight": 8, "nine": 9, "ten": 10, 
                          "page": 11, "knight": 12, "queen": 13, "king": 14}
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
                if hasattr(parent_widget, 'setTabIcon'):
                    tab_widget = parent_widget
                    break
                parent_widget = parent_widget.parent()
            
            # If we found a tab widget, update the tab icon
            if tab_widget:
                index = tab_widget.indexOf(self)
                if index >= 0:
                    # Create and set the cards-stack icon from theme or fallback
                    icon = QIcon.fromTheme("view-grid", 
                             QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "cards-stack.png")))
                    tab_widget.setTabIcon(index, icon)