from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea, QGroupBox, QToolBar, QPushButton, QTabWidget, QHBoxLayout, QTextEdit
from PyQt6.QtGui import QPixmap, QIcon, QAction, QColor, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
import os

class ColorDot(QIcon):
    """Creates a colored dot icon for tab decoration"""
    def __init__(self, color):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 8, 8)  # Draw a circle with 8px diameter
        painter.end()
        
        super().__init__(pixmap)

class CardViewTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)
    resized = pyqtSignal()  # Signal to handle resize events
    
    # Define color mapping for card types and suits
    COLOR_MAP = {
        "major_arcana": "#9c27b0",  # Purple for Major Arcana
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
        if not self.deck or not self.card:
            self.set_placeholder("No deck or card available")
            return
        
        main_layout = QVBoxLayout()
        
        # Create a splitter for image and information
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - card image in a better container
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(10, 10, 10, 10)  # Add padding around image
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumWidth(200)  # Set minimum width to prevent too small images
        
        # Add stretch above and below the image to center it vertically
        image_layout.addStretch(1)
        image_layout.addWidget(self.image_label)
        image_layout.addStretch(1)
        
        # Create scroll area with proper sizing policy
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(image_container)
        
        # Load and display the image
        self.load_image()
        
        splitter.addWidget(self.scroll_area)
        
        # Right side - tabbed card information
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tabbed widget for different information categories
        self.info_tabs = QTabWidget()
        self.info_tabs.setTabPosition(QTabWidget.TabPosition.East)  # Tabs on the right side
        
        # Tab 1: Overview
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        
        # Card name
        name_label = QLabel(self.card["name"])
        name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        overview_layout.addWidget(name_label)
        
        # Card ID
        id_label = QLabel(f"ID: {self.card['id']}")
        id_label.setStyleSheet("color: gray;")
        overview_layout.addWidget(id_label)

        # Card type
        type_label = QLabel(f"Type: {self.card['type'].replace('_', ' ').title()}")
        overview_layout.addWidget(type_label)
        
        # Card details based on type - using display names
        if self.card["type"] == "major_arcana":
            details_label = QLabel(f"Number: {self.card['number']}")
            overview_layout.addWidget(details_label)
        else:
            # Use display_suit and display_rank if available
            suit_name = self.card.get("display_suit", self.card['suit'].capitalize())
            rank_name = self.card.get("display_rank", self.card['rank'].capitalize())
            details_label = QLabel(f"Suit: {suit_name}\nRank: {rank_name}")
            overview_layout.addWidget(details_label)
            
        # Add deck information
        deck_label = QLabel(f"Deck: {self.deck.get_name()}")
        overview_layout.addWidget(deck_label)
        
        # Add description text to the overview tab
        if "alt_text" in self.card and self.card["alt_text"]:
            overview_layout.addSpacing(15)
            description_header = QLabel("Description:")
            description_header.setStyleSheet("font-weight: bold;")
            overview_layout.addWidget(description_header)
            
            description_label = QLabel(self.card["alt_text"])
            description_label.setWordWrap(True)
            description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            overview_layout.addWidget(description_label)
        
        # Add stretch to push everything to the top
        overview_layout.addStretch()
        
        # Add overview tab
        self.info_tabs.addTab(overview_tab, "Overview")
        
        # Tab 2: Esoterica 
        esoterica_tab = QWidget()
        esoterica_layout = QVBoxLayout(esoterica_tab)
        
        # Add some placeholder sections for esoteric content
        esoterica_header = QLabel("Esoteric Correspondences")
        esoterica_header.setStyleSheet("font-size: 16px; font-weight: bold;")
        esoterica_layout.addWidget(esoterica_header)
        
        # Placeholder sections
        for section in ["Elements", "Astrology", "Numerology", "Kabbalah", "Alchemy"]:
            section_label = QLabel(f"{section}:")
            section_label.setStyleSheet("font-weight: bold;")
            esoterica_layout.addWidget(section_label)
            
            placeholder = QLabel("Information will be added in the future.")
            placeholder.setStyleSheet("color: gray; font-style: italic; margin-left: 10px;")
            esoterica_layout.addWidget(placeholder)
            esoterica_layout.addSpacing(10)
        
        esoterica_layout.addStretch()
        self.info_tabs.addTab(esoterica_tab, "Esoterica")
        
        # Tab 3: Notes
        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        
        notes_header = QLabel("Personal Notes")
        notes_header.setStyleSheet("font-size: 16px; font-weight: bold;")
        notes_layout.addWidget(notes_header)
        
        # Add text editor for notes
        notes_edit = QTextEdit()
        notes_edit.setPlaceholderText("Enter your personal notes about this card here...")
        notes_layout.addWidget(notes_edit)
        
        # Add a save button
        save_btn = QPushButton("Save Notes")
        save_btn.setMaximumWidth(150)
        # Connect to a save function (to be implemented)
        # save_btn.clicked.connect(self.save_notes)
        notes_layout.addWidget(save_btn)
        
        self.info_tabs.addTab(notes_tab, "Notes")
        
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
        
        # Calculate available space (account for padding)
        available_width = self.scroll_area.width() - 40  # Account for padding and scrollbar
        available_height = self.scroll_area.height() - 40
        
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