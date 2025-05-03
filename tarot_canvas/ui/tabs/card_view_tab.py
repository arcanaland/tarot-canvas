from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea, 
                           QGroupBox, QToolBar, QPushButton, QTabWidget, QHBoxLayout, 
                           QTextEdit, QGridLayout, QFrame, QComboBox)
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
        
        # Add deck switching controls at the bottom of the image container
        self.deck_controls = QWidget()
        self.deck_controls.setMaximumHeight(40)  # Limit height for compact display
        deck_controls_layout = QHBoxLayout(self.deck_controls)
        deck_controls_layout.setContentsMargins(0, 5, 0, 0)
        
        # Previous deck button
        self.prev_deck_btn = QPushButton()
        self.prev_deck_btn.setIcon(QIcon.fromTheme("go-previous"))
        self.prev_deck_btn.setToolTip("Previous Deck")
        self.prev_deck_btn.clicked.connect(self.switch_to_previous_deck)
        self.prev_deck_btn.setFixedWidth(30)
        deck_controls_layout.addWidget(self.prev_deck_btn)
        
        # Deck selection combo box
        self.deck_combo = QComboBox()
        self.deck_combo.currentIndexChanged.connect(self.on_deck_selected)
        deck_controls_layout.addWidget(self.deck_combo, 1)  # Give combo box stretch priority
        
        # Next deck button
        self.next_deck_btn = QPushButton()
        self.next_deck_btn.setIcon(QIcon.fromTheme("go-next"))
        self.next_deck_btn.setToolTip("Next Deck")
        self.next_deck_btn.clicked.connect(self.switch_to_next_deck)
        self.next_deck_btn.setFixedWidth(30)
        deck_controls_layout.addWidget(self.next_deck_btn)
        
        # Add controls to image layout but hide initially (will show if multiple decks available)
        self.deck_controls.setVisible(False)
        image_layout.addWidget(self.deck_controls)  # Now anchored at the bottom
        
        # Create scroll area with proper sizing policy
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(image_container)
        
        # Load and display the image
        self.load_image()
        
        # Find compatible decks and update the deck switching UI
        self.find_compatible_decks()
        
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

        # Card name at the top
        name_label = QLabel(self.card["name"])
        name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        overview_layout.addWidget(name_label)

        # Card ID below name (kept separate as requested)
        id_label = QLabel(f"ID: {self.card['id']}")
        id_label.setStyleSheet("color: gray;")
        overview_layout.addWidget(id_label)

        # Create a grid for structured information
        info_grid = QGridLayout()
        info_grid.setVerticalSpacing(8)
        info_grid.setHorizontalSpacing(12)
        info_grid.setColumnStretch(1, 1)  # Make value column expandable

        # Add a frame around the structured info
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_frame.setFrameShadow(QFrame.Shadow.Sunken)
        info_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0.03);")
        info_frame.setLayout(info_grid)

        # Add card type (always present)
        type_label = QLabel("Type:")
        type_label.setStyleSheet("font-weight: bold;")
        type_value = QLabel(self.card['type'].replace('_', ' ').title())
        info_grid.addWidget(type_label, 0, 0, Qt.AlignmentFlag.AlignTop)
        info_grid.addWidget(type_value, 0, 1, Qt.AlignmentFlag.AlignTop)

        # Row counter for dynamic fields
        row = 1

        # Add suit and rank for minor arcana
        if self.card["type"] == "minor_arcana":
            # Suit
            suit_label = QLabel("Suit:")
            suit_label.setStyleSheet("font-weight: bold;")
            suit_name = self.card.get("display_suit", self.card['suit'].capitalize())
            suit_value = QLabel(suit_name)
            info_grid.addWidget(suit_label, row, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(suit_value, row, 1, Qt.AlignmentFlag.AlignTop)
            row += 1
            
            # Rank
            rank_label = QLabel("Rank:")
            rank_label.setStyleSheet("font-weight: bold;")
            rank_name = self.card.get("display_rank", self.card['rank'].capitalize())
            rank_value = QLabel(rank_name)
            info_grid.addWidget(rank_label, row, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(rank_value, row, 1, Qt.AlignmentFlag.AlignTop)
            row += 1

        # Add number for major arcana
        elif self.card["type"] == "major_arcana":
            number_label = QLabel("Number:")
            number_label.setStyleSheet("font-weight: bold;")
            number_value = QLabel(str(self.card['number']))
            info_grid.addWidget(number_label, row, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(number_value, row, 1, Qt.AlignmentFlag.AlignTop)
            row += 1

        # Add deck (always present)
        deck_label = QLabel("Deck:")
        deck_label.setStyleSheet("font-weight: bold;")
        deck_value = QLabel(f"<a href='deck:{self.deck.deck_path}'>{self.deck.get_name()}</a>")
        deck_value.setTextFormat(Qt.TextFormat.RichText)
        deck_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        deck_value.setOpenExternalLinks(False)
        deck_value.linkActivated.connect(self.on_deck_link_clicked)
        info_grid.addWidget(deck_label, row, 0, Qt.AlignmentFlag.AlignTop)
        info_grid.addWidget(deck_value, row, 1, Qt.AlignmentFlag.AlignTop)

        # Add the frame to the layout with some spacing
        overview_layout.addSpacing(10)
        overview_layout.addWidget(info_frame)
        overview_layout.addSpacing(10)

        # Add description text to the overview tab
        if "alt_text" in self.card and self.card["alt_text"]:
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
    
    def on_deck_link_clicked(self, link):
        """Handle clicks on the deck link"""
        if link.startswith('deck:'):
            deck_path = link[5:]  # Remove 'deck:' prefix
            print(f"DEBUG: Extracted deck path: {deck_path}")
            
            # Check if deck path is valid
            if not deck_path or deck_path == "None" or not os.path.exists(deck_path):
                # If it's the reference deck but has invalid path, use a different method
                if self.deck == deck_manager.get_reference_deck():
                    reference_deck = deck_manager.get_reference_deck()
                    self.navigation_requested.emit("open_deck_view", {
                        "deck_path": reference_deck.deck_path,
                        "source_tab_id": self.id
                    })
                    return
            
            # Emit signal to open the deck view
            self.navigation_requested.emit("open_deck_view", {
                "deck_path": deck_path,
                "source_tab_id": self.id
            })
    
    def find_compatible_decks(self):
        """Find all decks that contain this card (by ID) with an image and populate the deck selector"""
        if not self.card:
            return
        
        card_id = self.card.get("id")
        if not card_id:
            return
        
        # Get all decks
        all_decks = deck_manager.get_all_decks()
        self.compatible_decks = []
        
        # Find decks that have this card ID WITH an image
        for deck in all_decks:
            card = deck.get_card_by_id(card_id)
            if card and card.get("image") and os.path.exists(card.get("image", "")):
                self.compatible_decks.append((deck, card))
        
        # Only show controls if we have more than one deck
        if len(self.compatible_decks) <= 1:
            self.deck_controls.setVisible(False)
            return
        
        # Populate combobox
        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        
        current_index = 0
        for i, (deck, _) in enumerate(self.compatible_decks):
            self.deck_combo.addItem(deck.get_name(), deck.deck_path)
            if deck.deck_path == self.deck.deck_path:
                current_index = i
        
        self.deck_combo.setCurrentIndex(current_index)
        self.deck_combo.blockSignals(False)
        
        # Show the controls
        self.deck_controls.setVisible(True)

    def on_deck_selected(self, index):
        """Handle selection of a different deck from the dropdown"""
        if index < 0 or index >= len(self.compatible_decks):
            return
        
        # Get the selected deck and card
        new_deck, new_card = self.compatible_decks[index]
        
        # Only proceed if this is actually a different deck
        if new_deck.deck_path == self.deck.deck_path:
            return
        
        # Hide components during update
        self.scroll_area.setVisible(False)
        self.info_tabs.setVisible(False)
        
        # Update the current deck and card
        self.deck = new_deck
        self.card = new_card
        
        # Update the components
        self.load_image()
        self.update_deck_info()
        self.update_tab_name()
        
        # Show components again
        self.scroll_area.setVisible(True)
        self.info_tabs.setVisible(True)

    def load_and_refresh_image(self):
        """Clean load and display of the new card image"""
        # Load the new image
        self.load_image()
        
        # Update the tab name and icon
        self.update_tab_name()
        
        # Force a layout update
        self.layout.update()
        self.update()

    def update_deck_info(self):
        """Update card information in the overview tab without recreating everything"""
        # Find the overview tab
        for i in range(self.info_tabs.count()):
            if self.info_tabs.tabText(i) == "Overview":
                overview_tab = self.info_tabs.widget(i)
                break
        else:
            return  # Overview tab not found
        
        # Find all QLabels in the tab
        labels = overview_tab.findChildren(QLabel)
        
        # Update card name
        for label in labels:
            if label.font().bold() and label.font().pointSize() > 12:
                label.setText(self.card["name"])
                break
        
        # Update alt text/description
        description_found = False
        for i, label in enumerate(labels):
            if label.text() == "Description:" and i+1 < len(labels):
                # The next label should be the description
                desc_label = labels[i+1]
                if "alt_text" in self.card and self.card["alt_text"]:
                    desc_label.setText(self.card["alt_text"])
                    desc_label.setVisible(True)
                    description_found = True
                else:
                    desc_label.setVisible(False)
                break
        
        # If we didn't find existing description but have one in the new card, add it
        if not description_found and "alt_text" in self.card and self.card["alt_text"]:
            # Find the layout
            layout = overview_tab.layout()
            if layout:
                # Add description header
                description_header = QLabel("Description:")
                description_header.setStyleSheet("font-weight: bold;")
                layout.addWidget(description_header)
                
                # Add description text
                description_label = QLabel(self.card["alt_text"])
                description_label.setWordWrap(True)
                description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(description_label)
        
        # Update the deck link in the info grid
        frames = overview_tab.findChildren(QFrame)
        for frame in frames:
            if frame.frameShape() == QFrame.Shape.StyledPanel:
                # This is likely our info frame
                grid_layout = frame.layout()
                if isinstance(grid_layout, QGridLayout):
                    # Look for the deck label and value
                    for row in range(grid_layout.rowCount()):
                        label_item = grid_layout.itemAtPosition(row, 0)
                        if label_item and label_item.widget() and isinstance(label_item.widget(), QLabel) and label_item.widget().text() == "Deck:":
                            # Found the deck row, update the value
                            value_item = grid_layout.itemAtPosition(row, 1)
                            if value_item and value_item.widget():
                                deck_value = value_item.widget()
                                if isinstance(deck_value, QLabel):
                                    deck_value.setText(f"<a href='deck:{self.deck.deck_path}'>{self.deck.get_name()}</a>")
                                    deck_value.setTextFormat(Qt.TextFormat.RichText)
                                    deck_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                                    deck_value.setOpenExternalLinks(False)
                                    if not deck_value.receivers(deck_value.linkActivated):
                                        deck_value.linkActivated.connect(self.on_deck_link_clicked)
                                    break

    def switch_to_previous_deck(self):
        """Switch to the previous deck in the list"""
        current_index = self.deck_combo.currentIndex()
        if current_index > 0:
            self.deck_combo.setCurrentIndex(current_index - 1)

    def switch_to_next_deck(self):
        """Switch to the next deck in the list"""
        current_index = self.deck_combo.currentIndex()
        if current_index < self.deck_combo.count() - 1:
            self.deck_combo.setCurrentIndex(current_index + 1)

    def update_overview_tab(self):
        """Recreate the entire UI with the new deck and card"""
        # Clear the current layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Re-create the UI with the current deck and card
        self.setup_ui()