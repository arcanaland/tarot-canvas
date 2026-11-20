"""A majors-only created deck's offer to take the minors too"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from tarot_canvas.ui.strings import DECK_VIEW


class MinorsOffer(QWidget):
    accepted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        text = QLabel(DECK_VIEW["add_minors_text"])
        text.setWordWrap(True)
        text.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.button = QPushButton(QIcon.fromTheme("list-add"), DECK_VIEW["add_minors"])
        self.button.clicked.connect(self.accepted)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text, 1)
        layout.addWidget(self.button)
