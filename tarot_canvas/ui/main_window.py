from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, 
                            QMenuBar, QMenu, QApplication, QMessageBox, QFileDialog,
                            QTabWidget, QHBoxLayout, QToolButton)
                            
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt
import os
import importlib.resources as pkg_resources

from importlib.resources import files
ICON_PATH = files('tarot_canvas.resources.icons').joinpath('icon.png')

# Import custom tab classes
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tarot Canvas")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setGeometry(100, 100, 800, 600)

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
        
        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
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
    
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        main_layout.addWidget(self.tab_widget)
        
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
        welcome_label = QLabel("Try choosing one of the following:")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome_label)

        # Button container
        button_layout = QHBoxLayout()
        
        # Buttons for different tab types
        canvas_btn = QPushButton("New Canvas")
        canvas_btn.clicked.connect(self.new_canvas_tab)
        button_layout.addWidget(canvas_btn)
        
        deck_btn = QPushButton("Random Deck")
        deck_btn.clicked.connect(self.new_deck_view_tab)
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
        self.close_welcome_tab()
        self.tab_widget.addTab(canvas_tab, "Canvas")
        self.tab_widget.setCurrentWidget(canvas_tab)

    def new_deck_view_tab(self):
        deck_tab = DeckViewTab()
        self.close_welcome_tab()
        self.tab_widget.addTab(deck_tab, "Deck View")
        self.tab_widget.setCurrentWidget(deck_tab)

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
            deck_tab = DeckViewTab(deck_path=selected_files[0])
            self.close_welcome_tab()
            self.tab_widget.addTab(deck_tab, os.path.basename(os.path.dirname(selected_files[0])))
            self.tab_widget.setCurrentWidget(deck_tab)

    def new_reading(self):
        self.new_canvas_tab()

    def show_preferences(self):
        print("Preferences")

    def toggle_fullscreen(self, checked):
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

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
