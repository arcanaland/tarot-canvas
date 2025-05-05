from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox
from PyQt6.QtGui import QIcon

class DeckSwitcher(QWidget):
    """Component for switching between different decks for the same card"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.compatible_decks = []
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the deck switcher UI"""
        self.setMaximumHeight(40)  # Limit height for compact display
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        
        # Previous deck button
        self.prev_deck_btn = QPushButton()
        self.prev_deck_btn.setIcon(QIcon.fromTheme("go-previous"))
        self.prev_deck_btn.setToolTip("Previous Deck")
        self.prev_deck_btn.clicked.connect(self.switch_to_previous_deck)
        self.prev_deck_btn.setFixedWidth(30)
        layout.addWidget(self.prev_deck_btn)
        
        # Deck selection combo box
        self.deck_combo = QComboBox()
        self.deck_combo.currentIndexChanged.connect(self.on_deck_selected)
        layout.addWidget(self.deck_combo, 1)  # Give combo box stretch priority
        
        # Next deck button
        self.next_deck_btn = QPushButton()
        self.next_deck_btn.setIcon(QIcon.fromTheme("go-next"))
        self.next_deck_btn.setToolTip("Next Deck")
        self.next_deck_btn.clicked.connect(self.switch_to_next_deck)
        self.next_deck_btn.setFixedWidth(30)
        layout.addWidget(self.next_deck_btn)
        
        # Hide initially (will show if multiple decks available)
        self.setVisible(False)
        
    def update_compatible_decks(self, card, current_deck, deck_manager):
        """Find all decks that contain this card with an image"""
        if not card:
            return
            
        card_id = card.get("id")
        if not card_id:
            return
            
        # Get all decks
        all_decks = deck_manager.get_all_decks()
        self.compatible_decks = []
        
        # Find decks that have this card ID WITH an image
        for deck in all_decks:
            card_instance = deck.get_card_by_id(card_id)
            if card_instance and card_instance.get("image") and os.path.exists(card_instance.get("image", "")):
                self.compatible_decks.append((deck, card_instance))
        
        # Only show controls if we have more than one deck
        if len(self.compatible_decks) <= 1:
            self.setVisible(False)
            return
            
        # Populate combobox
        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        
        current_index = 0
        for i, (deck, _) in enumerate(self.compatible_decks):
            self.deck_combo.addItem(deck.get_name(), deck.deck_path)
            if deck.deck_path == current_deck.deck_path:
                current_index = i
                
        self.deck_combo.setCurrentIndex(current_index)
        self.deck_combo.blockSignals(False)
        
        # Show the controls
        self.setVisible(True)
        
    def on_deck_selected(self, index):
        """Handle selection of a different deck from the dropdown"""
        if not self.parent_tab or index < 0 or index >= len(self.compatible_decks):
            return
            
        # Get the selected deck and card
        new_deck, new_card = self.compatible_decks[index]
        
        # Only proceed if this is actually a different deck
        if new_deck.deck_path == self.parent_tab.deck.deck_path:
            return
            
        # Tell the parent tab to switch decks
        self.parent_tab.switch_to_deck(new_deck, new_card)
        
    def switch_to_previous_deck(self):
        """Switch to the previous deck in the list"""
        current_index = self.deck_combo.currentIndex()
        if current_index > 0:
            self.deck_combo.setCurrentIndex(current_index - 1)
        else:
            self.deck_combo.setCurrentIndex(self.deck_combo.count() - 1)
            
    def switch_to_next_deck(self):
        """Switch to the next deck in the list"""
        current_index = self.deck_combo.currentIndex()
        if current_index < self.deck_combo.count() - 1:
            self.deck_combo.setCurrentIndex(current_index + 1)
        else:
            self.deck_combo.setCurrentIndex(0)

import os  # Required for path operations