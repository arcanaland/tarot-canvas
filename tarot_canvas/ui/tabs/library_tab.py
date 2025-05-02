from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import (
    QListWidget, QLabel, QHBoxLayout, QVBoxLayout, QWidget, QPushButton,
    QScrollArea, QFrame, QGridLayout, QListWidgetItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QFont
import os
from pathlib import Path
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.models.deck import TarotDeck

class DeckCard(QFrame):
    """Card-like widget to represent a deck in the library grid"""
    clicked = pyqtSignal(object)  # Signal emitted when clicked, passes the deck
    double_clicked = pyqtSignal(object)  # Signal for double-click
    
    def __init__(self, deck, parent=None):
        super().__init__(parent)
        self.deck = deck
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(220, 280)
        self.setMaximumSize(220, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Add basic hover effect
        self.setStyleSheet("""
            DeckCard {
                border: 1px solid #aaa;
                border-radius: 8px;
                background-color: rgba(40, 40, 40, 0.15);
            }
            DeckCard:hover {
                background-color: rgba(80, 80, 80, 0.25);
                border: 1px solid #ccc;
            }
        """)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Try to get card back or first card as thumbnail
        thumbnail_path = self.get_deck_thumbnail()
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if thumbnail_path and os.path.exists(thumbnail_path):
            pixmap = QPixmap(thumbnail_path)
            # Set a fixed height for the image while maintaining aspect ratio
            pixmap = pixmap.scaledToHeight(180, Qt.TransformationMode.SmoothTransformation)
            image_label.setPixmap(pixmap)
        else:
            image_label.setText("No Preview")
            image_label.setStyleSheet("background-color: #333; color: white; padding: 40px;")
            image_label.setFixedSize(120, 180)
        
        # Deck name
        name_label = QLabel(self.deck.get_name())
        name_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        
        # Deck info
        cards_count = len(self.deck._cards)
        creator = self.deck._metadata.get("deck", {}).get("creator", "Unknown")
        info_label = QLabel(f"{cards_count} cards • {creator}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(image_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        layout.addWidget(info_label)

    def get_deck_thumbnail(self):
        """Get a thumbnail image for the deck (first major arcana)"""
        major_arcana = self.deck.get_cards_by_type("major_arcana")
        if major_arcana:
            # Try to get The Fool (0) or any first card
            for card in major_arcana:
                if card.get("number") == 0 and card.get("image"):
                    return card.get("image")
            
            # If no Fool, just use the first card with an image
            for card in major_arcana:
                if card.get("image"):
                    return card.get("image")
                    
        return None
        
    def mousePressEvent(self, event):
        self.clicked.emit(self.deck)
        super().mousePressEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.deck)
        super().mouseDoubleClickEvent(event)

class LibraryTab(BaseTab):
    deck_selected = pyqtSignal(object)  # Signal when a deck is selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        main_layout = QVBoxLayout()
        
        # Create scrollable area for the deck grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Container widget for the grid
        container = QWidget()
        self.grid_layout = QGridLayout(container)
        self.grid_layout.setSpacing(20)
        
        # Populate the grid with deck cards
        self.populate_deck_grid()
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        
        # Add browser button
        browser_button = QPushButton("Browse for Additional Decks...")
        browser_button.clicked.connect(self.browse_for_deck)
        main_layout.addWidget(browser_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.layout.addLayout(main_layout)
    
    def populate_deck_grid(self):
        """Populate the grid with deck cards"""
        # Clear existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Get all available decks
        decks = deck_manager.get_all_decks()
        
        # Calculate the number of columns based on parent width
        if self.parent():
            parent_width = self.parent().width()
            columns = max(1, min(4, parent_width // 250))  # Adjust based on card width
        else:
            columns = 3  # Default
        
        # Add the deck cards to the grid
        row, col = 0, 0
        for deck in decks:
            deck_card = DeckCard(deck)
            # Connect to selection handler for single-click (selection only)
            deck_card.clicked.connect(lambda d: self.deck_selected.emit(d))
            # Connect double-click to open the deck
            deck_card.double_clicked.connect(self.on_deck_selected)
            
            self.grid_layout.addWidget(deck_card, row, col)
            
            # Move to the next column or row
            col += 1
            if col >= columns:
                col = 0
                row += 1
        
        # Add spacer to make sure cards align to the top
        self.grid_layout.setRowStretch(row + 1, 1)
    
    def on_deck_selected(self, deck):
        """Handle deck selection (double-click opens the deck)"""
        # Open a new tab with the selected deck
        from tarot_canvas.ui.main_window import MainWindow
        main_window = self.window()
        if hasattr(main_window, 'new_deck_view_tab'):
            main_window.new_deck_view_tab(deck_path=deck.deck_path)
    
    def browse_for_deck(self):
        """Open file dialog to browse for additional decks"""
        from PyQt6.QtWidgets import QFileDialog
        
        main_window = self.window()
        if hasattr(main_window, 'open_deck'):
            main_window.open_deck()
            
    def resizeEvent(self, event):
        """Handle resize events to adjust the grid layout"""
        # Re-populate the grid when the tab is resized
        self.populate_deck_grid()
        super().resizeEvent(event)