from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QSplitter, QScrollArea, 
                           QGroupBox, QToolBar, QPushButton, QTabWidget, QHBoxLayout, 
                           QTextEdit, QGridLayout, QFrame, QComboBox, QListWidget, QListWidgetItem,
                           QStackedWidget, QPlainTextEdit, QInputDialog, QMessageBox, QFileDialog, 
                           QTextBrowser, QApplication)
from PyQt6.QtGui import QPixmap, QIcon, QAction, QColor, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
import os
import time
import shutil
import re

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
        notes_tab = self.setup_notes_tab()
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
        else:
            self.deck_combo.setCurrentIndex(self.deck_combo.count() - 1)

    def switch_to_next_deck(self):
        """Switch to the next deck in the list"""
        current_index = self.deck_combo.currentIndex()
        if current_index < self.deck_combo.count() - 1:
            self.deck_combo.setCurrentIndex(current_index + 1)
        else:
            self.deck_combo.setCurrentIndex(0)

    def update_overview_tab(self):
        """Recreate the entire UI with the new deck and card"""
        # Clear the current layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Re-create the UI with the current deck and card
        self.setup_ui()

    def setup_notes_tab(self):
        """Set up the notes tab with a cleaner"""
        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        notes_layout.setContentsMargins(0, 0, 0, 0)  # Remove unnecessary margins
        
        # Splitter for note list and content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT PANEL - List of notes with compact controls
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(10, 10, 5, 10)
        
        # Notes list with add button in a toolbar-like layout
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 5)
        
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("font-weight: bold;")
        list_header.addWidget(notes_label)
        
        list_header.addStretch()
        
        # Create a small, icon-only add button
        add_button = QPushButton()
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.setToolTip("Create new note")
        add_button.setMaximumSize(24, 24)
        add_button.clicked.connect(self.create_new_note)
        list_header.addWidget(add_button)
        
        list_layout.addLayout(list_header)
        
        # Add the list widget
        self.notes_list = QListWidget()
        self.notes_list.setMinimumWidth(120)
        self.notes_list.currentItemChanged.connect(self.on_note_selected)
        list_layout.addWidget(self.notes_list)
        
        # Add compact button row below the list
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 5, 0, 0)
        button_row.setSpacing(2)  # Tighter spacing for a compact look
        
        # Small icon buttons for note operations
        delete_button = QPushButton()
        delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        delete_button.setToolTip("Delete selected note")
        delete_button.setMaximumSize(24, 24)
        delete_button.clicked.connect(self.delete_current_note)
        button_row.addWidget(delete_button)
        
        rename_button = QPushButton()
        rename_button.setIcon(QIcon.fromTheme("edit-rename"))
        rename_button.setToolTip("Rename selected note")
        rename_button.setMaximumSize(24, 24)
        rename_button.clicked.connect(self.rename_current_note)
        button_row.addWidget(rename_button)
        
        export_button = QPushButton()
        export_button.setIcon(QIcon.fromTheme("document-export"))
        export_button.setToolTip("Export selected note")
        export_button.setMaximumSize(24, 24)
        export_button.clicked.connect(self.export_current_note)
        button_row.addWidget(export_button)
        
        button_row.addStretch()
        list_layout.addLayout(button_row)
        
        # Add list panel to splitter
        splitter.addWidget(list_panel)
        
        # RIGHT PANEL - Note editor/viewer
        note_panel = QWidget()
        note_layout = QVBoxLayout(note_panel)
        note_layout.setContentsMargins(5, 10, 10, 10)
        
        # Stack for edit/preview modes
        self.note_stack = QStackedWidget()
        
        # Edit widget with markdown editor
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        
        self.note_editor = QPlainTextEdit()
        self.note_editor.setPlaceholderText("Write your notes here using Markdown...\n\n# Heading\n\n**Bold text**\n\n- List item")
        edit_layout.addWidget(self.note_editor)
        self.note_stack.addWidget(edit_widget)
        
        # Preview widget with markdown rendering
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.note_preview = QTextBrowser()
        self.note_preview.setOpenExternalLinks(True)
        preview_layout.addWidget(self.note_preview)
        self.note_stack.addWidget(preview_widget)
        
        note_layout.addWidget(self.note_stack)
        
        # Clean footer with minimal controls
        footer_bar = QHBoxLayout()
        footer_bar.setContentsMargins(0, 5, 0, 0)
        
        # Toggle Preview/Edit
        self.preview_button = QPushButton()
        self.preview_button.setCheckable(True)
        self.preview_button.setIcon(QIcon.fromTheme("document-preview"))
        self.preview_button.setToolTip("Toggle preview mode")
        self.preview_button.toggled.connect(self.toggle_preview_mode)
        footer_bar.addWidget(self.preview_button)
        
        footer_bar.addStretch()
        
        # Save button aligned right
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolTip("Save note")
        self.save_button.clicked.connect(self.save_current_note)
        footer_bar.addWidget(self.save_button)
        
        note_layout.addLayout(footer_bar)
        
        # Add note panel to splitter
        splitter.addWidget(note_panel)
        
        # Set initial splitter sizes (30% list, 70% editor)
        splitter.setSizes([300, 700])
        
        # Add the splitter to the main layout
        notes_layout.addWidget(splitter)
        
        # Load existing notes for this card
        self.load_card_notes()
        
        return notes_tab

    def load_card_notes(self):
        """Load existing notes for this card"""
        if not self.card:
            return
            
        card_id = self.card.get("id")
        if not card_id:
            return
        
        # Determine the notes directory path
        notes_dir = os.path.expanduser(f"~/.local/share/tarot-canvas/notes/{card_id}")
        
        # Create the directory if it doesn't exist
        os.makedirs(notes_dir, exist_ok=True)
        
        # Clear the current list
        self.notes_list.clear()
        
        # Load all markdown files in the directory
        note_files = []
        if os.path.exists(notes_dir):
            for filename in os.listdir(notes_dir):
                if filename.endswith(".md"):
                    file_path = os.path.join(notes_dir, filename)
                    # Get file stats
                    stats = os.stat(file_path)
                    # Save tuple of (modified time, filename, full path)
                    note_files.append((stats.st_mtime, filename, file_path))
        
        # Sort by modified time (newest first)
        note_files.sort(reverse=True)
        
        # Add to list widget
        for _, filename, file_path in note_files:
            # Parse the filename to get a nice display name
            display_name = filename
            if "_" in filename:
                # Remove timestamp prefix and extension
                parts = filename.split("_", 1)
                if len(parts) > 1:
                    display_name = parts[1].rsplit(".", 1)[0]
            
            # Create the item
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.notes_list.addItem(item)
        
        # Select the first note if available
        if self.notes_list.count() > 0:
            self.notes_list.setCurrentRow(0)
        else:
            # No notes yet, disable the editor
            self.note_editor.setEnabled(False)
            self.save_button.setEnabled(False)
            self.preview_button.setEnabled(False)

    def on_note_selected(self, current, previous):
        """Handle selection of a note in the list"""
        if not current:
            # Clear and disable the editor
            self.note_editor.clear()
            self.note_editor.setEnabled(False)
            self.save_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            return
        
        # Get the file path from the item
        file_path = current.data(Qt.ItemDataRole.UserRole)
        
        # Load the note content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set the content in the editor
            self.note_editor.setPlainText(content)
            
            # Also update the preview if in preview mode
            if self.preview_button.isChecked():
                self.update_preview()
            
            # Enable editor and buttons
            self.note_editor.setEnabled(True)
            self.save_button.setEnabled(True)
            self.preview_button.setEnabled(True)
        except Exception as e:
            print(f"Error loading note: {e}")
            self.note_editor.setPlainText(f"Error loading note: {e}")

    def create_new_note(self):
        """Create a new note for this card"""
        if not self.card:
            return
            
        card_id = self.card.get("id")
        if not card_id:
            return
        
        # Get a name for the new note
        name, ok = QInputDialog.getText(
            self, 
            "New Note", 
            "Enter a name for this note:",
            text="Untitled Note"
        )
        
        if not ok or not name:
            return
        
        # Generate filename with timestamp
        timestamp = int(time.time())
        safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        filename = f"{timestamp}_{safe_name}.md"
        
        # Create notes directory if it doesn't exist
        notes_dir = os.path.expanduser(f"~/.local/share/tarot-canvas/notes/{card_id}")
        os.makedirs(notes_dir, exist_ok=True)
        
        # Create the file
        file_path = os.path.join(notes_dir, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {name}\n\n")
            
            # Add to list
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.notes_list.insertItem(0, item)
            self.notes_list.setCurrentItem(item)
            
            # Focus the editor
            self.note_editor.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create note: {e}")

    def save_current_note(self):
        """Save the current note content"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        content = self.note_editor.toPlainText()
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Update the preview if in preview mode
            if self.preview_button.isChecked():
                self.update_preview()
            
            # Show temporary success message
            status_bar = QApplication.instance().activeWindow().statusBar()
            if status_bar:
                status_bar.showMessage("Note saved successfully", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save note: {e}")

    def toggle_preview_mode(self, checked):
        """Toggle between edit and preview modes"""
        if checked:
            # Switch to preview mode
            self.update_preview()
            self.note_stack.setCurrentIndex(1)
            self.preview_button.setText("Edit")
        else:
            # Switch to edit mode
            self.note_stack.setCurrentIndex(0)
            self.preview_button.setText("Preview")

    def update_preview(self):
        """Update the preview with rendered markdown"""
        content = self.note_editor.toPlainText()
        
        # Simple markdown to HTML conversion
        # In a real implementation, use a proper markdown library
        html = self.simple_markdown_to_html(content)
        
        # Set the HTML in the preview
        self.note_preview.setHtml(html)

    def simple_markdown_to_html(self, markdown):
        """Convert markdown to HTML (simplified version)"""
        # For a proper implementation, use a library like Python-Markdown
        # This is a very simplified version that handles basic formatting
        
        html = markdown
        
        # Headers
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Lists
        html = re.sub(r'^- (.+)$', r'<ul><li>\1</li></ul>', html, flags=re.MULTILINE)
        
        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        
        # Paragraphs
        html = re.sub(r'(?<!\n)\n(?!\n)(.+)', r'<br>\1', html)
        html = re.sub(r'\n\n(.+)', r'<p>\1</p>', html)
        
        return html

    def delete_current_note(self):
        """Delete the currently selected note"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Note",
            f"Are you sure you want to delete the note '{current_item.text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Get the file path
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Delete the file
        try:
            os.remove(file_path)
            
            # Remove from list
            row = self.notes_list.row(current_item)
            self.notes_list.takeItem(row)
            
            # If there are no more notes, disable the editor
            if self.notes_list.count() == 0:
                self.note_editor.clear()
                self.note_editor.setEnabled(False)
                self.save_button.setEnabled(False)
                self.preview_button.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete note: {e}")

    def rename_current_note(self):
        """Rename the currently selected note"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Get current name
        current_name = current_item.text()
        
        # Ask for new name
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Note",
            "Enter a new name for this note:",
            text=current_name
        )
        
        if not ok or not new_name or new_name == current_name:
            return
        
        # Get the file path
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Generate new filename
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Keep the timestamp prefix if it exists
        if "_" in filename:
            timestamp = filename.split("_", 1)[0]
            safe_name = new_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            new_filename = f"{timestamp}_{safe_name}.md"
        else:
            # If no timestamp, add one
            timestamp = int(time.time())
            safe_name = new_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            new_filename = f"{timestamp}_{safe_name}.md"
        
        new_file_path = os.path.join(dirname, new_filename)
        
        # Rename the file
        try:
            os.rename(file_path, new_file_path)
            
            # Update item
            current_item.setText(new_name)
            current_item.setData(Qt.ItemDataRole.UserRole, new_file_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not rename note: {e}")

    def export_current_note(self):
        """Export the currently selected note to a file"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Get the file path and content
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Ask for export location
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Note",
            os.path.expanduser(f"~/Documents/{current_item.text()}.md"),
            "Markdown Files (*.md);;All Files (*)"
        )
        
        if not export_path:
            return
        
        # Copy the file
        try:
            shutil.copy2(file_path, export_path)
            
            # Show success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"Note exported to {export_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not export note: {e}")