from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QLabel, QSplitter
from PyQt6.QtCore import Qt

class CardViewTab(BaseTab):
    def __init__(self, card_path=None, parent=None):
        super().__init__(parent)
        self.card_path = card_path
        self.setup_ui()
        
    def setup_ui(self):
        if self.card_path:
            self.load_card(self.card_path)
        else:
            self.set_placeholder("Select a card to view details")
    
    def load_card(self, card_path):
        # Create a splitter for image and information
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - card image
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        splitter.addWidget(self.image_label)
        
        # Right side - card information
        self.info_widget = QLabel()
        splitter.addWidget(self.info_widget)
        
        # Set initial splitter sizes
        splitter.setSizes([int(self.width() * 0.6), int(self.width() * 0.4)])
        
        self.layout.addWidget(splitter)
        
        # TODO: Load card image and data