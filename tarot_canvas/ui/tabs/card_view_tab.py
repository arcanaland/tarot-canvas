from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea,
                           QTabWidget, QHBoxLayout)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
import os

from tarot_canvas.ui.tabs.card_view.color_dot import ColorDot
from tarot_canvas.ui.tabs.card_view.overview_tab import OverviewTab
from tarot_canvas.ui.tabs.card_view.notes_tab import NotesTab
from tarot_canvas.ui.tabs.card_view.esoterica_tab import EsotericaTab
from tarot_canvas.ui.tabs.card_view.deck_switcher import DeckSwitcher

class CardViewTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)
    resized = pyqtSignal()  # Signal to handle resize events
    
    # Define color mapping for card types and suits
    COLOR_MAP = {
        "major_arcana": "#916de4",  # Purple for Major Arcana
        "wands": "#ff9800",         # Orange for Wands
        "cups": "#2196f3",          # Blue for Cups
        "swords": "#ffeb3b",        # Yellow for Swords
        "pentacles": "#4caf50",     # Green for Pentacles
        "default": "#9e9e9e"        # Gray for unknown
    }
    
    def __init__(self, card=None, deck=None, source_tab_id=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck or deck_manager.get_reference_deck()
        self.deck_manager = deck_manager
        self.source_tab_id = source_tab_id
        self.id = f"card_{id(self)}"
        
        if card is None and self.deck:
            self.card = self.deck.get_random_card()
        
        # Set the tab name to the card name when it's created
        self.tab_name = self.card["name"] if self.card else "Card View"
        
        self.setup_ui()
        
        # Call update_tab_name() after initialization to set the tab's name immediately
        # Use a short timer to ensure the widget is fully added to its parent first
        QTimer.singleShot(100, self.update_tab_name)
        
    def setup_ui(self):
        """Set up the card view tab UI"""
        # We're already using the BaseTab's VBoxLayout
        main_layout = QVBoxLayout()
        
        if not self.deck or not self.card:
            self.layout.addWidget(QLabel("No deck or card available"))
            return
        
        # Create a splitter for image and information
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - card image in a container with reduced padding
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        # Reduce padding from 10px to 5px
        image_layout.setContentsMargins(5, 5, 5, 5)
        
        # Create an inner container to hold the image and allow vertical centering
        image_inner_container = QWidget()
        image_inner_layout = QVBoxLayout(image_inner_container)
        image_inner_layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumWidth(200)
        
        # Add image to inner container with stretches for vertical centering
        image_inner_layout.addStretch(1)
        image_inner_layout.addWidget(self.image_label)
        image_inner_layout.addStretch(1)
        
        # Add the inner container to the main image layout
        image_layout.addWidget(image_inner_container)
        
        # Add deck switching controls
        self.deck_switcher = DeckSwitcher(self)
        image_layout.addWidget(self.deck_switcher)
        
        # Create scroll area with proper sizing policy
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(image_container)
        
        # Load and display the image
        self.load_image()
        
        # Find compatible decks and update the deck switching UI
        self.deck_switcher.update_compatible_decks(self.card, self.deck, deck_manager)
        
        splitter.addWidget(self.scroll_area)
        
        # Right side - tabbed card information
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tabbed widget for different information categories
        self.info_tabs = QTabWidget()
        self.info_tabs.setTabPosition(QTabWidget.TabPosition.East)  # Tabs on the right side
        
        # Tab 1: Overview
        self.overview_tab = OverviewTab(self.card, self.deck, self)
        self.info_tabs.addTab(self.overview_tab, "Overview")
        
        # Tab 2: Esoterica
        self.esoterica_tab = EsotericaTab(self.card, self)
        self.info_tabs.addTab(self.esoterica_tab, "Esoterica")
        
        # Tab 3: Notes
        self.notes_tab = NotesTab(self)
        self.info_tabs.addTab(self.notes_tab, "Notes")
        
        # Load the notes for this card
        self.notes_tab.load_card_notes(self.card)
        
        # Add the tabbed widget to the info layout
        info_layout.addWidget(self.info_tabs)
        
        splitter.addWidget(info_widget)
        
        # Set initial splitter sizes
        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Set the main layout
        self.layout.addLayout(main_layout)
        
        # Connect resize event to update image size
        self.resized.connect(self.resize_image)
    
    def load_image(self):
        """Load and initially display the card image"""
        if self.card and "image" in self.card and self.card["image"] and os.path.exists(self.card["image"]):
            self.original_pixmap = QPixmap(self.card["image"])
            # Display the image at original size first
            self.image_label.setPixmap(self.original_pixmap)
            # Then schedule a resize
            QTimer.singleShot(50, self.resize_image)
        else:
            self.image_label.setText("No image available")
            self.original_pixmap = None
            
    def resize_image(self):
        """Resize the image to fit the available space while maintaining aspect ratio"""
        if not hasattr(self, 'original_pixmap') or not self.original_pixmap:
            return
        
        # Get available width and height from scroll area
        if not hasattr(self, 'scroll_area') or not self.scroll_area:
            return
        
        # Calculate available space (account for reduced padding)
        available_width = self.scroll_area.width() - 20  # Reduced from 40 to 20 (5px padding on each side)
        available_height = self.scroll_area.height() - 20
        
        # Get original image dimensions
        pixmap_width = self.original_pixmap.width()
        pixmap_height = self.original_pixmap.height()
        
        # Use reasonable default if dimensions are 0
        if pixmap_width <= 0 or pixmap_height <= 0:
            self.image_label.setPixmap(self.original_pixmap)
            return
        
        # Calculate scaling factor
        width_scale = available_width / pixmap_width
        height_scale = available_height / pixmap_height
        
        # Use smaller scale to ensure image fits
        scale = min(width_scale, height_scale, 1.0)  # Don't scale up images larger than original
        
        # Apply scaling
        new_width = int(pixmap_width * scale)
        new_height = int(pixmap_height * scale)
        
        # Create scaled pixmap
        scaled_pixmap = self.original_pixmap.scaled(
            new_width, 
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Apply to label
        self.image_label.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        self.resized.emit()
    
    def update_tab_name(self):
        """Update the tab name and add color dot based on card type/suit"""
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
                
                # If we found a tab widget, update the tab text and icon
                if tab_widget:
                    index = tab_widget.indexOf(self)
                    if index >= 0:
                        # Update tab text
                        tab_widget.setTabText(index, self.card["name"])
                        
                        # Create and set a colored dot icon based on card type/suit
                        color = self.get_card_color()
                        dot_icon = ColorDot(color)
                        tab_widget.setTabIcon(index, dot_icon)
                
                # If parent is a QStackedWidget inside a tab widget
                if hasattr(parent, 'parent') and hasattr(parent.parent(), 'setTabText'):
                    tab_widget = parent.parent()
                    index = tab_widget.indexOf(parent)
                    if index >= 0:
                        tab_widget.setTabText(index, self.card["name"])
                        
                        # Create and set a colored dot icon based on card type/suit
                        color = self.get_card_color()
                        dot_icon = ColorDot(color)
                        tab_widget.setTabIcon(index, dot_icon)
    
    def get_card_color(self):
        """Get the appropriate color for this card based on its type/suit"""
        if not self.card:
            return self.COLOR_MAP["default"]
            
        card_type = self.card.get("type", "")
        
        if card_type == "major_arcana":
            return self.COLOR_MAP["major_arcana"]
        elif card_type == "minor_arcana":
            suit = self.card.get("suit", "")
            return self.COLOR_MAP.get(suit, self.COLOR_MAP["default"])
        else:
            return self.COLOR_MAP["default"]
    
    def navigate_back(self):
        """Navigate back to the source tab"""
        if self.source_tab_id:
            self.navigation_requested.emit("navigate", self.source_tab_id)
    
    def switch_to_deck(self, new_deck, new_card):
        """Switch to a different deck's version of the current card"""
        # Hide components during update
        self.scroll_area.setVisible(False)
        self.info_tabs.setVisible(False)
        
        # Update the current deck and card
        self.deck = new_deck
        self.card = new_card
        
        # Update the components
        self.load_image()
        
        # Update the overview tab with the new card and deck info
        self.overview_tab.update_card_info(new_card, new_deck)
        
        # Update the notes tab for the new card
        self.notes_tab.load_card_notes(new_card)
        
        # Update the esoterica tab
        if hasattr(self.esoterica_tab, 'update_card_info') and callable(getattr(self.esoterica_tab, 'update_card_info', None)):
            self.esoterica_tab.update_card_info(new_card)
        
        # Update the tab name in the parent tab widget
        self.update_tab_name()
        
        # Update deck switcher to reflect current selection
        self.deck_switcher.update_compatible_decks(new_card, new_deck, self.deck_manager)
        
        # Show components again
        self.scroll_area.setVisible(True)
        self.info_tabs.setVisible(True)