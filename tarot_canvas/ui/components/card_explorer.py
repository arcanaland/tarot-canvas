from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QLabel, QHeaderView
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from tarot_canvas.models.deck_manager import deck_manager

class CardExplorerPanel(QWidget):
    # Signal emitted when a card action is requested
    card_action_requested = pyqtSignal(str, dict, object)  # action, card, deck
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.populate_tree()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header label
        header = QLabel("Card Explorer")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(header)
        
        # Tree view
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(15)
        
        # IMPORTANT: Disable editing to prevent rename on double-click
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        
        # Connect signals
        self.tree_view.clicked.connect(self.on_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        
        # Create model
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        
        layout.addWidget(self.tree_view)
        
        # Set initial size
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
    
    def populate_tree(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Cards"])
        
        # Get all available decks
        decks = deck_manager.get_all_decks()
        
        for deck in decks:
            # Create deck item
            deck_item = QStandardItem(deck.get_name())
            deck_item.setData({"type": "deck", "deck": deck}, Qt.ItemDataRole.UserRole)
            
            # Create Major Arcana group
            major_group = QStandardItem("Major Arcana")
            major_group.setData({"type": "group", "group": "major_arcana", "deck": deck}, Qt.ItemDataRole.UserRole)
            
            # Add Major Arcana cards
            major_cards = deck.get_cards_by_type("major_arcana")
            for card in major_cards:
                card_item = QStandardItem(card["name"])
                card_item.setData({"type": "card", "card": card, "deck": deck}, Qt.ItemDataRole.UserRole)
                major_group.appendRow(card_item)
            
            deck_item.appendRow(major_group)
            
            # Create suit groups
            suits = deck.get_suits()
            for suit in suits:
                suit_group = QStandardItem(suit.capitalize())
                suit_group.setData({"type": "group", "group": suit, "deck": deck}, Qt.ItemDataRole.UserRole)
                
                # Add cards for this suit
                suit_cards = deck.get_cards_by_suit(suit)
                for card in suit_cards:
                    card_item = QStandardItem(card["name"])
                    card_item.setData({"type": "card", "card": card, "deck": deck}, Qt.ItemDataRole.UserRole)
                    suit_group.appendRow(card_item)
                
                deck_item.appendRow(suit_group)
            
            self.model.appendRow(deck_item)
        
        # Expand the first deck by default
        if self.model.rowCount() > 0:
            first_deck_index = self.model.index(0, 0)
            self.tree_view.expand(first_deck_index)
    
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
            print(f"Double-clicked on card: {data['card']['name']}")