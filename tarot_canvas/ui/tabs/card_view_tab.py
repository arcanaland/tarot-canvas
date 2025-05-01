from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea, QPushButton
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
import os

class CardViewTab(BaseTab):
    def __init__(self, card=None, deck=None, parent=None):
        super().__init__(parent)
        self.deck = deck or deck_manager.get_reference_deck()
        
        if card is None and self.deck:
            self.card = self.deck.get_random_card()
        else:
            self.card = card
            
        self.setup_ui()
        
    def setup_ui(self):
        if not self.deck or not self.card:
            self.set_placeholder("No deck or card available")
            return
            
        # Create a splitter for image and information
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - card image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Load the image if available
        if self.card["image"] and os.path.exists(self.card["image"]):
            pixmap = QPixmap(self.card["image"])
            self.image_label.setPixmap(pixmap.scaled(400, 700, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.image_label.setText("No image available")
            
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.image_label)
        splitter.addWidget(scroll_area)
        
        # Right side - card information
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        
        # Card name
        name_label = QLabel(self.card["name"])
        name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        info_layout.addWidget(name_label)
        
        # Card type
        type_label = QLabel(f"Type: {self.card['type'].replace('_', ' ').title()}")
        info_layout.addWidget(type_label)
        
        # Card details based on type
        if self.card["type"] == "major_arcana":
            details_label = QLabel(f"Number: {self.card['number']}")
            info_layout.addWidget(details_label)
        else:
            details_label = QLabel(f"Suit: {self.card['suit'].capitalize()}\nRank: {self.card['rank'].capitalize()}")
            info_layout.addWidget(details_label)
            
        # Card ID
        id_label = QLabel(f"ID: {self.card['id']}")
        id_label.setStyleSheet("color: gray;")
        info_layout.addWidget(id_label)
        
        # Add deck information
        deck_label = QLabel(f"Deck: {self.deck.get_name()}")
        info_layout.addWidget(deck_label)
        
        # Add "Pick Another" button
        pick_another_btn = QPushButton("Pick Another Random Card")
        pick_another_btn.clicked.connect(self.pick_another_card)
        info_layout.addWidget(pick_another_btn)
        
        info_layout.addStretch()
        splitter.addWidget(info_widget)
        
        # Set initial splitter sizes
        splitter.setSizes([int(self.width() * 0.6), int(self.width() * 0.4)])
        
        self.layout.addWidget(splitter)
        
    def pick_another_card(self):
        """Replace this tab with a new random card tab"""
        if self.deck:
            # Get parent tab widget
            parent = self.parent()
            if parent:
                # Create new card tab
                new_card_tab = CardViewTab(deck=self.deck)
                
                # Get current index
                index = parent.indexOf(self)
                
                # Insert new tab and remove old one
                parent.insertTab(index, new_card_tab, "Card View")
                parent.removeTab(index + 1)
                parent.setCurrentIndex(index)