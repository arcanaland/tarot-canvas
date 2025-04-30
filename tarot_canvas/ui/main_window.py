from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import os

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tarot Canvas")
        self.setWindowIcon(QIcon(os.path.join("resources", "icons", "tarot_icon.png")))
        self.setGeometry(100, 100, 800, 600)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        label = QLabel("Welcome to Tarot Canvas!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        print("Open Tarot Deck clicked")
