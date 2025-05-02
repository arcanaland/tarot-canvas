from PyQt6.QtWidgets import QLabel, QVBoxLayout, QFrame, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont
import os

class CardThumbnail(QFrame):
    """Widget for displaying a card thumbnail in the deck view"""
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()  # New signal for double clicks
    
    def __init__(self, card, deck_path, size=QSize(100, 160), parent=None):
        super().__init__(parent)
        self.card = card
        self.deck_path = deck_path
        self.thumbnail_size = size
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(self.thumbnail_size)
        self.setMaximumSize(self.thumbnail_size)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # Card image thumbnail
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setMinimumSize(self.thumbnail_size.width() - 4, self.thumbnail_size.height() - 20)
        self.image_label.setMaximumSize(self.thumbnail_size.width() - 4, self.thumbnail_size.height() - 20)
        
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
                self.image_label.setPixmap(pixmap.scaled(
                    self.image_label.width(), 
                    self.image_label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                ))
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