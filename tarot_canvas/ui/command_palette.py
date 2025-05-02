from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                           QLabel, QHBoxLayout, QWidget, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QKeySequence, QShortcut

from tarot_canvas.models.deck_manager import deck_manager
import os

class CommandPaletteItem(QWidget):
    """Custom widget for command palette items with card image thumbnail"""
    
    def __init__(self, card, deck, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Card thumbnail
        image_path = card.get("image")
        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            icon_label = QLabel()
            pixmap = pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(25, 40)
            layout.addWidget(icon_label)
        else:
            # Placeholder if no image
            empty_label = QLabel()
            empty_label.setFixedSize(25, 40)
            layout.addWidget(empty_label)
        
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


class CommandPalette(QDialog):
    card_selected = pyqtSignal(dict, object)  # Card data, Deck
    
    def __init__(self, parent=None, active_tab_type=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
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
        
        # Initially populate with reference deck cards
        self.populate_results(self.cards)
    
    def populate_results(self, card_deck_pairs):
        """Populate the results list with the given cards"""
        self.results_list.clear()
        
        for card, deck in card_deck_pairs:
            # Create list item
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 60))  # Set appropriate height
            
            # Create and add custom widget
            card_widget = CommandPaletteItem(card, deck)
            
            # Set action hint based on active tab type
            action_text = "Add to Canvas" if self.active_tab_type == "canvas" else "Open"
            card_widget.set_action_hint(action_text)
            
            # Store card and deck data with the item
            item.setData(Qt.ItemDataRole.UserRole, (card, deck))
            
            # Add to list
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, card_widget)
        
        # Select first item if available
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
    
    def filter_results(self):
        """Filter results based on search text"""
        search_text = self.search_input.text().lower()
        
        if not search_text:
            # Show all cards
            self.populate_results(self.cards)
            return
        
        # Filter cards by name, type, suit, and rank
        filtered_cards = []
        for card, deck in self.cards:
            card_name = card.get("name", "").lower()
            card_type = card.get("type", "").lower()
            card_suit = card.get("suit", "").lower()
            card_rank = card.get("rank", "").lower()
            deck_name = deck.get_name().lower()
            
            # Check if any field contains the search text
            if (search_text in card_name or 
                search_text in card_type or 
                search_text in card_suit or 
                search_text in card_rank or
                search_text in deck_name):
                filtered_cards.append((card, deck))
        
        # Populate with filtered results
        self.populate_results(filtered_cards)
    
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
            if current_item:
                self.on_item_activated(current_item)
        elif event.key() == Qt.Key.Key_Up:
            # Handle up key when in search input
            if self.search_input.hasFocus() and self.results_list.count() > 0:
                current_row = self.results_list.currentRow()
                if current_row > 0:
                    self.results_list.setCurrentRow(current_row - 1)
                else:
                    self.results_list.setCurrentRow(self.results_list.count() - 1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Down:
            # Handle down key when in search input
            if self.search_input.hasFocus() and self.results_list.count() > 0:
                current_row = self.results_list.currentRow()
                if current_row < self.results_list.count() - 1:
                    self.results_list.setCurrentRow(current_row + 1)
                else:
                    self.results_list.setCurrentRow(0)
                event.accept()
                return
        
        # Pass unhandled events to parent
        super().keyPressEvent(event)