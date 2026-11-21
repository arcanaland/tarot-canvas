import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from tarot_canvas.models.deck_types import CardKind
from tarot_canvas.ui import typography
from tarot_canvas.ui.strings import CARD_VIEW

log = logging.getLogger(__name__)


class CardPreviewWidget(QFrame):
    """Tooltip-like widget that shows a preview of a tarot card when hovering over a link"""

    def __init__(self, parent=None):
        super().__init__(parent)
        log.debug("Creating CardPreviewWidget")

        # Set up styling as a floating panel
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            CardPreviewWidget {
                background-color: palette(window);
                border: 1px solid palette(mid);
                border-radius: 5px;
                padding: 0px;
            }
            QLabel {
                color: palette(text);
            }
        """)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Card image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(150, 250)
        layout.addWidget(self.image_label)

        # Card name
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        typography.apply(self.name_label, typography.Role.HEADING_4, primary=True)
        layout.addWidget(self.name_label)

        # Card suit/type
        self.type_label = QLabel()
        self.type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_label.setStyleSheet("font-style: italic; color: palette(mid-text);")
        layout.addWidget(self.type_label)

        # Hide initially
        self.hide()
        log.debug("CardPreviewWidget initialized and hidden")

    def set_card(self, card, deck=None):
        """Set the card data to display"""
        if not card:
            log.debug("No card provided to preview, hiding")
            self.hide()
            return

        log.debug("Setting up preview for card: %s", card.display_name)

        self.name_label.setText(card.display_name)

        card_type = ""
        if card.kind is CardKind.MAJOR:
            card_type = CARD_VIEW["major_arcana"]
        elif card.suit_key:
            card_type = f"{card.suit_key.title()}"
            if card.rank_key:
                card_type += f" - {card.rank_key}"

        log.debug("Card type/suit: %s", card_type)
        self.type_label.setText(card_type)

        if card.default_image():
            try:
                image_path = card.default_image()
                log.debug("Trying to load image from: %s", image_path)

                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    # Resize to fit in the preview
                    pixmap = pixmap.scaled(
                        150,
                        250,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.image_label.setPixmap(pixmap)
                    self.image_label.setFixedSize(pixmap.size())
                    log.debug(
                        "Image loaded successfully, size: %sx%s", pixmap.width(), pixmap.height()
                    )
                else:
                    log.debug("Failed to load image - pixmap is null")
                    self.image_label.setText(CARD_VIEW["preview_no_image"])
            except Exception as e:
                log.exception("Error loading card image: %s", e)
                self.image_label.setText(CARD_VIEW["preview_image_error"])
        else:
            log.debug("No image specified for card")
            self.image_label.setText(CARD_VIEW["preview_no_image"])

        # Resize the widget based on content
        self.adjustSize()
        log.debug("Preview widget size adjusted to: %sx%s", self.width(), self.height())
