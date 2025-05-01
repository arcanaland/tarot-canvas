from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea, QGroupBox, QToolBar, QPushButton
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtCore import Qt, pyqtSignal
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
import os

class CardViewTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)
    
    def __init__(self, card=None, deck=None, source_tab_id=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck or deck_manager.get_reference_deck()
        self.source_tab_id = source_tab_id
        self.id = f"card_{id(self)}"
        
        if card is None and self.deck:
            self.card = self.deck.get_random_card()
        
        # Set the tab name to the card name when it's created
        self.tab_name = self.card["name"] if self.card else "Card View"
        
        self.setup_ui()
        
        # Call update_tab_name() after initialization to set the tab's name immediately
        # Use a short timer to ensure the widget is fully added to its parent first
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.update_tab_name)
        
    def setup_ui(self):
        if not self.deck or not self.card:
            self.set_placeholder("No deck or card available")
            return
        
        # Main layout setup
        main_layout = QVBoxLayout()
        
        # Add a back button to the top if we came from somewhere
        if self.source_tab_id:
            back_btn = QPushButton("← Back to Canvas")
            back_btn.clicked.connect(self.navigate_back)
            main_layout.addWidget(back_btn)
        
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
        
        # Card ID
        id_label = QLabel(f"ID: {self.card['id']}")
        id_label.setStyleSheet("color: gray;")
        info_layout.addWidget(id_label)

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
            
        # Add deck information
        deck_label = QLabel(f"Deck: {self.deck.get_name()}")
        info_layout.addWidget(deck_label)
        
        # Add description (alt_text) section
        description_group = QGroupBox("Description")
        description_layout = QVBoxLayout(description_group)
        
        # Create a scroll area for the description to handle long text
        description_scroll = QScrollArea()
        description_scroll.setWidgetResizable(True)
        
        description_content = QWidget()
        description_content_layout = QVBoxLayout(description_content)
        
        # Add the alt_text as a description if available
        if "alt_text" in self.card and self.card["alt_text"]:
            description_label = QLabel(self.card["alt_text"])
            description_label.setWordWrap(True)
            description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        else:
            description_label = QLabel("No description available for this card.")
            description_label.setStyleSheet("color: gray; font-style: italic;")
        
        description_content_layout.addWidget(description_label)
        description_content_layout.addStretch()
        
        description_scroll.setWidget(description_content)
        description_layout.addWidget(description_scroll)
        
        # Add the description group to the info layout
        info_layout.addWidget(description_group)
        
        info_layout.addStretch()
        splitter.addWidget(info_widget)
        
        # Set initial splitter sizes
        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Set the main layout
        self.layout.addLayout(main_layout)
            
    def update_tab_name(self):
        """Update the tab name to match the current card"""
        if self.card:
            parent = self.parent()
            if parent:
                # Find the tab widget that contains this widget
                tab_widget = None
                parent_widget = parent
                
                # Try to find a parent that has setTabText method (likely a QTabWidget)
                while parent_widget and not tab_widget:
                    if hasattr(parent_widget, 'setTabText'):
                        tab_widget = parent_widget
                        break
                    parent_widget = parent_widget.parent()
                
                # If we found a tab widget, update the tab text
                if tab_widget:
                    index = tab_widget.indexOf(self)
                    if index >= 0:
                        tab_widget.setTabText(index, self.card["name"])
                
                # If parent is a QStackedWidget inside a tab widget
                if hasattr(parent, 'parent') and hasattr(parent.parent(), 'setTabText'):
                    tab_widget = parent.parent()
                    index = tab_widget.indexOf(parent)
                    if index >= 0:
                        tab_widget.setTabText(index, self.card["name"])
    
    def navigate_back(self):
        """Navigate back to the source tab"""
        if self.source_tab_id:
            self.navigation_requested.emit("navigate", self.source_tab_id)