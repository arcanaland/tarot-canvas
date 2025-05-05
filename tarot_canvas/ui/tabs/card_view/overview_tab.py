from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame
from PyQt6.QtCore import Qt
import os

class OverviewTab(QWidget):
    """Tab displaying overview information about a tarot card"""
    
    def __init__(self, card=None, deck=None, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.card = card
        self.deck = deck
        
        # Create properties for both minor arcana and major arcana to avoid
        # having to recreate UI when switching between card types
        self.name_label = None
        self.id_label = None
        self.type_value = None
        self.deck_value = None
        self.info_frame = None
        self.info_grid = None
        
        # Minor arcana specific
        self.suit_value = None
        self.rank_value = None
        
        # Major arcana specific
        self.number_value = None
        
        # Description
        self.description_header = None
        self.description_label = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the overview tab UI"""
        layout = QVBoxLayout(self)

        if not self.card:
            layout.addWidget(QLabel("No card information available"))
            return

        # Card name at the top
        self.name_label = QLabel(self.card["name"])
        self.name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.name_label.setObjectName("name_label")
        layout.addWidget(self.name_label)

        # Card ID below name
        self.id_label = QLabel(f"ID: {self.card['id']}")
        self.id_label.setStyleSheet("color: gray;")
        self.id_label.setObjectName("id_label")
        layout.addWidget(self.id_label)

        # Create a grid for structured information
        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(8)
        self.info_grid.setHorizontalSpacing(12)
        self.info_grid.setColumnStretch(1, 1)  # Make value column expandable

        # Add a frame around the structured info
        self.info_frame = QFrame()
        self.info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.info_frame.setFrameShadow(QFrame.Shadow.Sunken)
        self.info_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0.03);")
        self.info_frame.setLayout(self.info_grid)

        # Add card type (always present)
        type_label = QLabel("Type:")
        type_label.setStyleSheet("font-weight: bold;")
        type_label.setObjectName("type_label")
        self.type_value = QLabel(self.card['type'].replace('_', ' ').title())
        self.type_value.setObjectName("type_value")
        self.info_grid.addWidget(type_label, 0, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.type_value, 0, 1, Qt.AlignmentFlag.AlignTop)

        # Row counter for dynamic fields
        row = 1

        # Create all possible fields for both card types, hide the ones we don't need
        
        # Create suit and rank fields (for minor arcana)
        suit_label = QLabel("Suit:")
        suit_label.setStyleSheet("font-weight: bold;")
        suit_label.setObjectName("suit_label")
        self.suit_value = QLabel()
        self.suit_value.setObjectName("suit_value")
        self.info_grid.addWidget(suit_label, 1, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.suit_value, 1, 1, Qt.AlignmentFlag.AlignTop)
        
        rank_label = QLabel("Rank:")
        rank_label.setStyleSheet("font-weight: bold;")
        rank_label.setObjectName("rank_label")
        self.rank_value = QLabel()
        self.rank_value.setObjectName("rank_value")
        self.info_grid.addWidget(rank_label, 2, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.rank_value, 2, 1, Qt.AlignmentFlag.AlignTop)
        
        # Create number field (for major arcana)
        number_label = QLabel("Number:")
        number_label.setStyleSheet("font-weight: bold;")
        number_label.setObjectName("number_label")
        self.number_value = QLabel()
        self.number_value.setObjectName("number_value")
        self.info_grid.addWidget(number_label, 3, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.number_value, 3, 1, Qt.AlignmentFlag.AlignTop)
        
        # Add deck (always present)
        deck_label = QLabel("Deck:")
        deck_label.setStyleSheet("font-weight: bold;")
        deck_label.setObjectName("deck_label")
        self.deck_value = QLabel()
        self.deck_value.setObjectName("deck_value")
        self.update_deck_link() # Set the deck link
        self.deck_value.setTextFormat(Qt.TextFormat.RichText)
        self.deck_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.deck_value.setOpenExternalLinks(False)
        self.deck_value.linkActivated.connect(self.on_deck_link_clicked)
        self.info_grid.addWidget(deck_label, 4, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.deck_value, 4, 1, Qt.AlignmentFlag.AlignTop)

        # Add the frame to the layout with some spacing
        layout.addSpacing(10)
        layout.addWidget(self.info_frame)
        layout.addSpacing(10)

        # Add description text to the overview tab
        self.description_header = QLabel("Description:")
        self.description_header.setStyleSheet("font-weight: bold;")
        self.description_header.setObjectName("description_header")
        layout.addWidget(self.description_header)
        
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description_label.setObjectName("description_label")
        layout.addWidget(self.description_label)

        # Add stretch to push everything to the top
        layout.addStretch()
        
        # Now show/hide and update the appropriate fields based on the current card
        self.update_card_info(self.card, self.deck)
    
    def update_deck_link(self):
        """Update the deck link in the overview tab"""
        if self.deck and self.deck_value:
            self.deck_value.setText(f"<a href='deck:{self.deck.deck_path}'>{self.deck.get_name()}</a>")
    
    def on_deck_link_clicked(self, link):
        """Handle clicks on the deck link"""
        if self.parent_tab and link.startswith('deck:'):
            deck_path = link[5:]  # Remove 'deck:' prefix
            
            # Check if deck path is valid
            if not deck_path or deck_path == "None" or not os.path.exists(deck_path):
                # If it's the reference deck but has invalid path, use a different method
                if self.deck == self.parent_tab.deck_manager.get_reference_deck():
                    reference_deck = self.parent_tab.deck_manager.get_reference_deck()
                    self.parent_tab.navigation_requested.emit("open_deck_view", {
                        "deck_path": reference_deck.deck_path,
                        "source_tab_id": self.parent_tab.id
                    })
                    return
            
            # Emit signal to open the deck view
            self.parent_tab.navigation_requested.emit("open_deck_view", {
                "deck_path": deck_path,
                "source_tab_id": self.parent_tab.id
            })
    
    def update_card_info(self, card, deck):
        """Update the overview tab with new card and deck information"""
        if not card:
            return
            
        self.card = card
        self.deck = deck
        
        # Update basic info - directly update the labels
        if self.name_label:
            self.name_label.setText(card["name"])
            
        if self.id_label:
            self.id_label.setText(f"ID: {card['id']}")
            
        if self.type_value:
            self.type_value.setText(card['type'].replace('_', ' ').title())
        
        # Show/hide appropriate fields based on card type
        if card["type"] == "minor_arcana":
            # Show minor arcana fields
            if self.suit_value and self.rank_value:
                suit_name = card.get("display_suit", card['suit'].capitalize())
                rank_name = card.get("display_rank", card['rank'].capitalize())
                self.suit_value.setText(suit_name)
                self.rank_value.setText(rank_name)
                
                # Make them visible
                self.suit_value.parentWidget().setVisible(True)
                self.suit_value.setVisible(True)
                self.rank_value.parentWidget().setVisible(True)
                self.rank_value.setVisible(True)
            
            # Hide major arcana fields
            if self.number_value:
                self.number_value.parentWidget().setVisible(False)
                self.number_value.setVisible(False)
                
        elif card["type"] == "major_arcana":
            # Show major arcana fields
            if self.number_value:
                self.number_value.setText(str(card['number']))
                
                # Make it visible
                self.number_value.parentWidget().setVisible(True)
                self.number_value.setVisible(True)
            
            # Hide minor arcana fields
            if self.suit_value and self.rank_value:
                self.suit_value.parentWidget().setVisible(False)
                self.suit_value.setVisible(False)
                self.rank_value.parentWidget().setVisible(False)
                self.rank_value.setVisible(False)
        
        # Update deck link
        self.update_deck_link()
        
        # Update description
        has_description = "alt_text" in card and card["alt_text"]
        
        if has_description and self.description_label and self.description_header:
            self.description_label.setText(card["alt_text"])
            self.description_header.setVisible(True)
            self.description_label.setVisible(True)
        elif self.description_label and self.description_header:
            self.description_header.setVisible(False)
            self.description_label.setVisible(False)