from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeView, QLabel, QHeaderView, 
                            QComboBox, QHBoxLayout, QFrame)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from tarot_canvas.models.deck_manager import deck_manager

class CardExplorerPanel(QWidget):
    # Signal emitted when a card action is requested
    card_action_requested = pyqtSignal(str, dict, object)  # action, card, deck
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_deck = None
        self.setup_ui()
        self.populate_deck_selector()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header label
        header = QLabel("Card Explorer")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(header)
        
        # Tree view for cards
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(15)
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        
        # Connect signals
        self.tree_view.clicked.connect(self.on_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        
        # Create model
        self.model = QStandardItemModel()
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
        deck_layout.addWidget(self.deck_selector, 1)  # 1 = stretch factor
        
        layout.addLayout(deck_layout)
        
        # Set initial size
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
    
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
        major_group.setData({"type": "group", "group": "major_arcana", "deck": self.current_deck}, 
                           Qt.ItemDataRole.UserRole)
        
        # Add Major Arcana cards
        major_cards = self.current_deck.get_cards_by_type("major_arcana")
        for card in major_cards:
            card_item = QStandardItem(card["name"])
            card_item.setData({"type": "card", "card": card, "deck": self.current_deck}, 
                             Qt.ItemDataRole.UserRole)
            major_group.appendRow(card_item)
        
        self.model.appendRow(major_group)
        
        # Create suit groups
        suits = self.current_deck.get_suits()
        for suit in suits:
            suit_group = QStandardItem(suit.capitalize())
            suit_group.setData({"type": "group", "group": suit, "deck": self.current_deck}, 
                              Qt.ItemDataRole.UserRole)
            
            # Add cards for this suit
            suit_cards = self.current_deck.get_cards_by_suit(suit)
            for card in suit_cards:
                card_item = QStandardItem(card["name"])
                card_item.setData({"type": "card", "card": card, "deck": self.current_deck}, 
                                 Qt.ItemDataRole.UserRole)
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