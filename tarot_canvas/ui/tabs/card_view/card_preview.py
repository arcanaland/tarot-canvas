from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QSize
from tarot_canvas.utils.logger import logger

class CardPreviewWidget(QFrame):
    """Tooltip-like widget that shows a preview of a tarot card when hovering over a link"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("Creating CardPreviewWidget")
        
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
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.name_label)
        
        # Card suit/type
        self.type_label = QLabel()
        self.type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_label.setStyleSheet("font-style: italic; color: palette(mid-text);")
        layout.addWidget(self.type_label)
        
        # Hide initially
        self.hide()
        logger.debug("CardPreviewWidget initialized and hidden")
    
    def set_card(self, card, deck=None):
        """Set the card data to display"""
        if not card:
            logger.debug("No card provided to preview, hiding")
            self.hide()
            return
            
        logger.debug(f"Setting up preview for card: {card.get('name', 'Unknown')}")
            
        # Set card name
        card_name = card.get('name', 'Unknown Card')
        self.name_label.setText(card_name)
        
        # Determine card type/suit
        card_type = ""
        card_id = card.get('id', '')
        if 'major_arcana' in card_id:
            card_type = "Major Arcana"
        elif 'suit' in card:
            card_type = f"{card['suit'].title()}"
            if 'rank' in card:
                card_type += f" - {card['rank']}"
        
        logger.debug(f"Card type/suit: {card_type}")
        self.type_label.setText(card_type)
        
        if 'image' in card and card['image']:
            try:
                # Use the image path that's already stored in the card dictionary
                image_path = card['image']
                logger.debug(f"Trying to load image from: {image_path}")
                
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    # Resize to fit in the preview
                    pixmap = pixmap.scaled(
                        150, 250, 
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.image_label.setPixmap(pixmap)
                    self.image_label.setFixedSize(pixmap.size())
                    logger.debug(f"Image loaded successfully, size: {pixmap.width()}x{pixmap.height()}")
                else:
                    logger.debug("Failed to load image - pixmap is null")
                    self.image_label.setText("No Image")
            except Exception as e:
                logger.error(f"Error loading card image: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                self.image_label.setText("Image Error")
        else:
            logger.debug("No image specified for card")
            self.image_label.setText("No Image")
        
        # Resize the widget based on content
        self.adjustSize()
        logger.debug(f"Preview widget size adjusted to: {self.width()}x{self.height()}")