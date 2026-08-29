import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class CardThumbnail(QFrame):
    """Widget for displaying a card thumbnail in the deck view"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()  # New signal for double clicks

    def __init__(self, card, deck_path, size=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck_path = deck_path
        self.thumbnail_size = size or QSize(100, 160)
        # Box available to the image, once margins and the name label are taken out.
        self.image_size = QSize(self.thumbnail_size.width() - 4, self.thumbnail_size.height() - 20)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(self.thumbnail_size)
        self.setMaximumSize(self.thumbnail_size)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Card image thumbnail (letterboxed)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(self.image_size)
        self.image_label.setMaximumSize(self.image_size)

        # Card name label
        self.name_label = QLabel(self.card.get("name", "Unknown"))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setFont(QFont("Arial", 8))
        self.name_label.setMaximumHeight(16)

        # Load image
        self.load_image()

        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)

    def load_image(self):
        image_path = self.card.get("image")
        if image_path:
            # Image path is already absolute in the TarotDeck class
            if os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                if pixmap.isNull():
                    self.image_label.setText("Image not found")
                    return
                self.image_label.setPixmap(
                    pixmap.scaled(
                        self.image_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.image_label.setText("Image not found")
        else:
            self.image_label.setText("No image")

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        # Highlight on hover
        self.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); border-radius: 5px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Remove highlight
        self.setStyleSheet("")
        super().leaveEvent(event)
