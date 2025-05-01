from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, 
                            QMenuBar, QMenu, QApplication, QMessageBox, QFileDialog)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt
import os
import importlib.resources as pkg_resources

from importlib.resources import files
ICON_PATH = files('tarot_canvas.resources.icons').joinpath('icon.png')

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
        
        new_action = QAction("&New Canvas", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_reading)
        file_menu.addAction(new_action)
        
        open_action = QAction("&Open Deck", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_deck)
        file_menu.addAction(open_action)
        
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
        label.setText("Try summoning a card?")
        layout.addWidget(label)

        # Button to open a tarot deck
        open_deck_btn = QPushButton("Open Tarot Deck")
        open_deck_btn.clicked.connect(self.open_deck)
        layout.addWidget(open_deck_btn)

        # Set the central widget
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def open_deck(self):
        # Placeholder for opening a tarot deck
        file_dialog = QFileDialog()
        file_dialog.setNameFilter("Tarot Decks (deck.toml);;All Files (*)")
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            print(f"Selected file: {selected_files[0]}")

    def new_reading(self):
        print("New reading")

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
