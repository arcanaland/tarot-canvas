from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea, 
                            QFrame, QHBoxLayout, QSizePolicy)
from PyQt6.QtCore import Qt
from tarot_canvas.models.esoterica import esoterica_manager
from tarot_canvas.utils.logger import logger

class PassageWidget(QFrame):
    """Widget to display a single book/source passage"""
    
    def __init__(self, passage, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.03);")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Source metadata
        source_meta = passage.get("source", {})
        source_name = source_meta.get("name", "Unknown Source")
        source_author = source_meta.get("author", "Unknown Author")
        
        # Header (book/source title)
        header = QLabel(source_name)
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)
        
        # Author
        author = QLabel(f"by {source_author}")
        author.setStyleSheet("font-style: italic; color: #555;")
        layout.addWidget(author)
        
        # Text
        text = passage.get("text", "")
        html_text = text.replace("\n\n", "<p>").replace("\n", "<br>")
        
        text_label = QLabel()
        text_label.setWordWrap(True)
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setText(html_text)
        layout.addWidget(text_label)

class EsotericaTab(QWidget):
    """Tab displaying esoteric information about a tarot card"""
    
    def __init__(self, card=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.parent_tab = parent
        
        # Currently displayed passages
        self.passage_widgets = []
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the esoterica tab UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 5)
        
        header_label = QLabel("Esoteric References")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # Container widget with margins
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 5, 10, 10)
        self.content_layout.setSpacing(20)
        
        # No content label (shown when no passages are available)
        self.no_content_label = QLabel("No esoteric content available for this card.")
        self.no_content_label.setStyleSheet("color: #777; font-style: italic; padding: 20px;")
        self.no_content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.no_content_label)
        
        # Add stretch to push content to the top
        self.content_layout.addStretch()
        
        # Set the scroll area widget
        scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(scroll_area)
        
        # Update content for the current card
        self.update_card_info(self.card)
        
    def update_card_info(self, card):
        """Update displayed content based on the card"""
        self.card = card
        
        # Clear any existing passage widgets
        self.clear_passages()
        
        if not card:
            logger.debug("No card provided to EsotericaTab.update_card_info")
            self.show_no_content()
            return
            
        # Get the card ID
        card_id = card.get("id", "")
        if not card_id:
            logger.debug("Card has no ID")
            self.show_no_content()
            return
            
        logger.debug(f"Looking for passages for card: {card_id}")
        
        # Get all passages for this card
        passages = esoterica_manager.get_passages_for_card(card_id)
        
        if not passages:
            logger.debug(f"No passages found for card: {card_id}")
            self.show_no_content()
            return
            
        logger.debug(f"Found {len(passages)} passages for card: {card_id}")
        
        # We have content, hide the no content label
        self.no_content_label.setVisible(False)
        
        # Add a widget for each passage
        for passage in passages:
            passage_widget = PassageWidget(passage, self)
            self.content_layout.insertWidget(self.content_layout.count() - 1, passage_widget)
            self.passage_widgets.append(passage_widget)
        
    def clear_passages(self):
        """Remove all passage widgets"""
        for widget in self.passage_widgets:
            self.content_layout.removeWidget(widget)
            widget.deleteLater()
        self.passage_widgets = []
        
    def show_no_content(self):
        """Show the 'no content available' message"""
        self.no_content_label.setVisible(True)