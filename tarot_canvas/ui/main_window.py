from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, 
                            QMenuBar, QMenu, QApplication, QMessageBox, QFileDialog,
                            QTabWidget, QHBoxLayout, QToolButton, QSplitter)
                            
from PyQt6.QtGui import QIcon, QAction, QActionGroup
from PyQt6.QtCore import Qt
import os
import importlib.resources as pkg_resources

from pathlib import Path
from importlib.resources import files
ICON_PATH = files('tarot_canvas.resources.icons').joinpath('icon.png')

# Import custom tab classes
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab

# Import the card explorer panel
from tarot_canvas.ui.components.card_explorer import CardExplorerPanel

# Import log viewer and logger
from tarot_canvas.ui.windows.log_viewer import LogViewerDialog
from tarot_canvas.utils.logger import TarotLogger
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType
from tarot_canvas.utils.logger import logger
from tarot_canvas.models.deck_manager import deck_manager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tarot Canvas")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setGeometry(100, 100, 950, 600)

        # Initialize theme manager
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.on_theme_changed)
        
        # Apply current theme
        self.theme_manager._apply_theme()
        
        self.create_menus()
        self.init_ui()

    def create_menus(self):
        # Create menu bar
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        
        new_menu = QMenu("&New", self)
        file_menu.addMenu(new_menu)
        
        new_canvas_action = QAction("&Canvas", self)
        new_canvas_action.setShortcut("Ctrl+N")
        new_canvas_action.triggered.connect(self.new_canvas_tab)
        new_menu.addAction(new_canvas_action)
        
                
        new_card_view_action = QAction("&Card View", self)
        new_card_view_action.setShortcut("Ctrl+T")
        new_card_view_action.triggered.connect(self.new_card_view_tab)
        new_menu.addAction(new_card_view_action)
        
        new_deck_view_action = QAction("&Deck View", self)
        new_deck_view_action.triggered.connect(self.new_deck_view_tab)
        new_menu.addAction(new_deck_view_action)
        
        new_library_action = QAction("&Library", self)
        new_library_action.triggered.connect(self.new_library_tab)
        new_menu.addAction(new_library_action)

        
        open_action = QAction("&Open Deck", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_deck)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        close_tab_action = QAction("Close &Tab", self)
        close_tab_action.setShortcut("Ctrl+W")
        close_tab_action.triggered.connect(self.close_current_tab)
        file_menu.addAction(close_tab_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")
        
        preferences_action = QAction("&Preferences", self)
        preferences_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(preferences_action)
        
        # View menu
        view_menu = menu_bar.addMenu("&View")
        
        # Add explorer toggle to View menu
        self.explorer_action = QAction("&Card Explorer", self)
        self.explorer_action.setShortcut("Ctrl+E")
        self.explorer_action.setCheckable(True)
        self.explorer_action.setChecked(True)  # Set checked by default
        self.explorer_action.triggered.connect(self.toggle_card_explorer)
        view_menu.addAction(self.explorer_action)
        
        view_menu.addSeparator()
        
        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        # Add Theme submenu
        theme_menu = QMenu("&Theme", self)
        view_menu.addMenu(theme_menu)
        
        # Create a theme action group for radio behavior
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        
        # System theme action
        system_theme_action = QAction("&System Default", self)
        system_theme_action.setCheckable(True)
        system_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.SYSTEM))
        theme_group.addAction(system_theme_action)
        theme_menu.addAction(system_theme_action)
        
        # Light theme action
        light_theme_action = QAction("&Light", self)
        light_theme_action.setCheckable(True)
        light_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.LIGHT))
        theme_group.addAction(light_theme_action)
        theme_menu.addAction(light_theme_action)
        
        # Dark theme action
        dark_theme_action = QAction("&Dark", self)
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.DARK))
        theme_group.addAction(dark_theme_action)
        theme_menu.addAction(dark_theme_action)
        
        # Set the checked state based on current theme
        current_theme = ThemeManager.get_instance().get_current_theme()
        if current_theme == ThemeType.SYSTEM:
            system_theme_action.setChecked(True)
        elif current_theme == ThemeType.LIGHT:
            light_theme_action.setChecked(True)
        elif current_theme == ThemeType.DARK:
            dark_theme_action.setChecked(True)
        
        # Store theme actions for later reference
        self.theme_actions = {
            ThemeType.SYSTEM: system_theme_action,
            ThemeType.LIGHT: light_theme_action,
            ThemeType.DARK: dark_theme_action
        }
        
        # Tools menu
        tools_menu = menu_bar.addMenu("&Tools")
        
        # Add Log Viewer action
        log_viewer_action = QAction("&Log Viewer", self)
        log_viewer_action.triggered.connect(self.show_log_viewer)
        tools_menu.addAction(log_viewer_action)
        
        # About menu
        about_menu = menu_bar.addMenu("&About")
        
        about_action = QAction("&About Tarot Canvas", self)
        about_action.triggered.connect(self.show_about)
        about_menu.addAction(about_action)

    def init_ui(self):
        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)  # Set smaller margins (left, top, right, bottom)
        main_layout.setSpacing(2)  # Reduce spacing between widgets
    
        # Create splitter for explorer panel and tab area
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Create and add card explorer panel (hidden by default)
        self.card_explorer = CardExplorerPanel()
        self.card_explorer.card_action_requested.connect(self.on_explorer_card_selected)
        self.card_explorer.card_action_requested.connect(self.on_card_action_requested)
        self.card_explorer.show()  # Show by default
        self.main_splitter.addWidget(self.card_explorer)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.main_splitter.addWidget(self.tab_widget)
        
        # Set appropriate sizes for splitter
        width = self.width()
        self.main_splitter.setSizes([int(width * 0.2), int(width * 0.8)])
        
        main_layout.addWidget(self.main_splitter)
        
        # Set the central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Add a welcome tab
        self.add_welcome_tab()

    def add_welcome_tab(self):
        welcome_tab = QWidget()
        layout = QVBoxLayout()

        label = QLabel("Welcome to Tarot Canvas!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add app icon in the center
        icon_label = QLabel()
        icon_pixmap = QIcon(str(ICON_PATH)).pixmap(128, 128)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Change label text
        welcome_label = QLabel("Select a card on the left or choose an option below:")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome_label)

        # Button container
        button_layout = QHBoxLayout()
        
        # Buttons for different tab types
        canvas_btn = QPushButton("New Canvas")
        canvas_btn.clicked.connect(self.new_canvas_tab)
        button_layout.addWidget(canvas_btn)
        
        deck_btn = QPushButton("Open Standard Deck")
        deck_btn.clicked.connect(self.open_reference_deck)
        button_layout.addWidget(deck_btn)
        
        library_btn = QPushButton("Deck Library")
        library_btn.clicked.connect(self.new_library_tab)
        button_layout.addWidget(library_btn)
        
        card_btn = QPushButton("Pick Random Card")
        card_btn.clicked.connect(self.new_card_view_tab)
        button_layout.addWidget(card_btn)
        
        layout.addLayout(button_layout)
        welcome_tab.setLayout(layout)
        
        self.tab_widget.addTab(welcome_tab, "Welcome")

    def close_welcome_tab(self):
        """Close the welcome tab if it exists"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Welcome":
                self.tab_widget.removeTab(i)
                break

    def new_canvas_tab(self):
        canvas_tab = CanvasTab()
        canvas_tab.navigation_requested.connect(self.handle_tab_navigation)
        self.close_welcome_tab()
        self.tab_widget.addTab(canvas_tab, "Canvas")
        self.tab_widget.setCurrentWidget(canvas_tab)
        return canvas_tab

    def handle_tab_navigation(self, action, data):
        """Handle navigation between tabs"""
        if action == "open_card_view":
            # Extract the data
            card = data.get("card")
            deck = data.get("deck")
            source_tab_id = data.get("source_tab_id")
            
            # Check if a tab for this card already exists
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if hasattr(tab, 'id') and hasattr(tab, 'card') and tab.card and tab.card.get('id') == card.get('id'):
                    # Tab exists, just select it
                    self.tab_widget.setCurrentWidget(tab)
                    return
            
            # Create a new card view tab
            from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
            card_tab = CardViewTab(card=card, deck=deck, source_tab_id=source_tab_id)
            card_tab.navigation_requested.connect(self.handle_tab_navigation)
            
            # Add it to the tab widget
            self.tab_widget.addTab(card_tab, card.get("name", "Card"))
            self.tab_widget.setCurrentWidget(card_tab)
            
        elif action == "navigate":
            # Navigate to a specific tab by ID
            tab_id = data
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if hasattr(tab, 'id') and tab.id == tab_id:
                    self.tab_widget.setCurrentWidget(tab)
                    break

    def new_deck_view_tab(self, deck_path=None):
        deck_tab = DeckViewTab(deck_path=deck_path)
        deck_tab.card_action_requested.connect(self.on_card_action_requested)
        
        # Close welcome tab if needed
        self.close_welcome_tab()
        
        # Add tab with initial title
        initial_title = "Deck View"
        if deck_path:
            initial_title = os.path.basename(deck_path)
        
        tab_index = self.tab_widget.addTab(deck_tab, initial_title)
        
        # Set current to this tab
        self.tab_widget.setCurrentWidget(deck_tab)
        
        # Immediately try to update the title if we have a deck loaded
        if deck_path and hasattr(deck_tab, 'deck') and deck_tab.deck:
            pretty_name = deck_tab.deck.get_name()
            self.tab_widget.setTabText(tab_index, pretty_name)
            print(f"Setting tab title to: {pretty_name}")
        
        # Still connect the signal for future updates
        deck_tab.title_changed.connect(
            lambda new_title: self.tab_widget.setTabText(self.tab_widget.indexOf(deck_tab), new_title)
        )
        
        return deck_tab

    def new_library_tab(self):
        library_tab = LibraryTab()
        self.close_welcome_tab()
        self.tab_widget.addTab(library_tab, "Library")
        self.tab_widget.setCurrentWidget(library_tab)

    def new_card_view_tab(self):
        card_tab = CardViewTab()
        self.close_welcome_tab()
        self.tab_widget.addTab(card_tab, "Card View")
        self.tab_widget.setCurrentWidget(card_tab)

    def close_tab(self, index):
        if self.tab_widget.count() > 1:  # Keep at least one tab open
            self.tab_widget.removeTab(index)
        else:
            # If it's the last tab, replace it with welcome
            self.tab_widget.removeTab(index)
            self.add_welcome_tab()

    def close_current_tab(self):
        current_index = self.tab_widget.currentIndex()
        self.close_tab(current_index)

    def open_deck(self):
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Tarot Decks (deck.toml);;All Files (*)")
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            print(f"Selected file: {selected_files[0]}")
            deck_path = Path(selected_files[0]).parent.resolve()
            deck_tab = self.new_deck_view_tab(deck_path=deck_path)

    def new_reading(self):
        self.new_canvas_tab()

    def show_preferences(self):
        print("Preferences")

    def toggle_fullscreen(self, checked):
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def toggle_card_explorer(self, checked):
        """Toggle visibility of the card explorer panel"""
        if checked:
            self.card_explorer.show()
            # Adjust splitter sizes to show explorer with reasonable width
            width = self.main_splitter.width()
            self.main_splitter.setSizes([int(width * 0.2), int(width * 0.8)])
        else:
            self.card_explorer.hide()
            # Collapse explorer completely
            self.main_splitter.setSizes([0, self.main_splitter.width()])
    
    def on_explorer_card_selected(self, action, card, deck):
        """Handle card selection from explorer panel (original handler)"""
        # Skip handling if it's a different action than viewing
        if action != "view_card" and action != "use_card":
            return
            
        # Check if we already have a tab open for this card
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'id') and hasattr(tab, 'card') and tab.card and tab.card.get('id') == card.get('id'):
                # Tab exists, just select it
                self.tab_widget.setCurrentWidget(tab)
                return
        
        # Create a new card view tab
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
        card_tab = CardViewTab(card=card, deck=deck)
        card_tab.navigation_requested.connect(self.handle_tab_navigation)
        
        # Add it to the tab widget
        self.tab_widget.addTab(card_tab, card.get("name", "Card"))
        self.tab_widget.setCurrentWidget(card_tab)

    def on_card_action_requested(self, action, card, deck):
        """Handle all card actions from the explorer based on context"""
        current_tab = self.tab_widget.currentWidget()

        if action == "double_click":            
            # Check if the current tab is a canvas tab
            if hasattr(current_tab, 'id') and current_tab.id.startswith('canvas_'):
                # If it's a canvas tab, add the card to it
                if hasattr(current_tab, 'add_specific_card'):
                    current_tab.add_specific_card(card, deck)
                    print(f"Adding card to canvas: {card['name']}")
            else:
                # For any other tab type, open a card view
                self.open_card_view_tab(card, deck)
                print(f"Opening card view for: {card['name']}")
        elif action == "use_card":
            # Check if the current tab is a canvas tab
            if hasattr(current_tab, 'id') and 'canvas_' in current_tab.id:
                # If it's a canvas tab, add the card to it
                if hasattr(current_tab, 'add_specific_card'):
                    current_tab.add_specific_card(card, deck)
            else:
                # Default to opening a card view for non-canvas tabs
                self.on_explorer_card_selected("view_card", card, deck)
        elif action == "view_card":
            # Always open the card view for this action
            self.on_explorer_card_selected(action, card, deck)

    def open_card_view_tab(self, card, deck):
        """Open a new tab to view a specific card"""
        # Check if we already have a tab open for this card
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'id') and hasattr(tab, 'card') and tab.card and tab.card.get('id') == card.get('id'):
                # Tab exists, just select it
                self.tab_widget.setCurrentWidget(tab)
                return
        
        # Create a new card view tab
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
        card_tab = CardViewTab(card=card, deck=deck)
        card_tab.navigation_requested.connect(self.handle_tab_navigation)
        
        # Add it to the tab widget
        self.tab_widget.addTab(card_tab, card.get("name", "Card"))
        self.tab_widget.setCurrentWidget(card_tab)

    def show_about(self):
        about_text = (
            "Tarot Canvas\n\n"
            "Version: 0.1.0\n"
            "A modern tarot exploration application.\n\n"
            "© 2025 Arcana Land"
        )
        QMessageBox.about(self, "About Tarot Canvas", about_text)

    def open_card_view(self, card, deck=None):
        """Open a card view tab for a specific card
        
        Args:
            card (dict): Card dictionary
            deck (TarotDeck, optional): Deck the card belongs to
        """
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
        
        # Create a card view tab
        tab = CardViewTab(card=card, deck=deck, parent=self.tab_widget)
        
        # Add it to the tab widget
        self.tab_widget.addTab(tab, card["name"])
        
        # Select the new tab
        self.tab_widget.setCurrentWidget(tab)

    def show_log_viewer(self):
        """Show the log viewer dialog"""
        log_viewer = LogViewerDialog(self)
        log_viewer.exec()

    def change_theme(self, theme_type):
        """Change the application theme"""
        logger.info(f"Changing theme to: {theme_type.value}")
        ThemeManager.get_instance().set_theme(theme_type)

    def on_theme_changed(self, theme_name):
        """Handle theme change events"""
        logger.info(f"Theme changed to: {theme_name}")
        
        # Update checked state of theme actions
        try:
            theme = ThemeType(theme_name)
            for t, action in self.theme_actions.items():
                action.setChecked(t == theme)
        except (ValueError, AttributeError) as e:
            logger.error(f"Error updating theme actions: {e}")

    def open_reference_deck(self):
        """Open the reference deck from the deck manager"""
        # Get reference deck from deck manager
        reference_deck = deck_manager.get_reference_deck()
        
        if not reference_deck:
            QMessageBox.warning(self, "Deck Not Found", 
                              "The reference deck could not be loaded.")
            return
        
        # Create a deck view tab with the reference deck path
        deck_tab = self.new_deck_view_tab(deck_path=reference_deck.deck_path)
        self.close_welcome_tab()
