from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout

from tarot_canvas.models.deck import pick_raster
from tarot_canvas.ui.canvas.detail import art_loader, art_size, fit_device_size


class CardThumbnail(QFrame):
    """Widget for displaying a card thumbnail in the deck view"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    copy_requested = pyqtSignal()

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
        self._dpr = self.devicePixelRatioF()
        target = self.image_size.height() * self._dpr
        image_path = pick_raster(self.card.get("images", {}), target) or self.card.get("image")
        if not image_path:
            self.image_label.setText("No image")
            return
        source = art_size(image_path)
        if not source.isValid() or source.isEmpty():
            self.image_label.setText("Image not found")
            return
        size = fit_device_size(source, self.image_size, self._dpr)
        if not size.isEmpty():
            art_loader().request(self, image_path, size, 1)

    def receive_detail(self, level, image):
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self._dpr)
        self.image_label.setPixmap(pixmap)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def card_menu(self):
        """Open does what a double-click does and Copy asks the owner to copy"""
        menu = QMenu(self)
        open_action = menu.addAction(QIcon.fromTheme("document-open"), "&Open Card")
        open_action.triggered.connect(self.double_clicked)
        copy_action = menu.addAction(QIcon.fromTheme("edit-copy"), "&Copy Card")
        copy_action.triggered.connect(self.copy_requested)
        return menu

    def contextMenuEvent(self, event):
        menu = self.card_menu()
        menu.exec(event.globalPos())
        menu.deleteLater()

    def enterEvent(self, event):
        # Highlight on hover
        self.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); border-radius: 5px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Remove highlight
        self.setStyleSheet("")
        super().leaveEvent(event)
