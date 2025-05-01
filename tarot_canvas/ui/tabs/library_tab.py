from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QListWidget, QLabel, QHBoxLayout, QVBoxLayout, QWidget

class LibraryTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        # Create a horizontal layout
        h_layout = QHBoxLayout()
        
        # Create a list widget for deck selection
        self.deck_list = QListWidget()
        self.deck_list.setMaximumWidth(200)
        h_layout.addWidget(self.deck_list)
        
        # Create info panel for selected deck
        self.info_panel = QWidget()
        info_layout = QVBoxLayout(self.info_panel)
        
        self.deck_title = QLabel("Select a deck")
        self.deck_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        info_layout.addWidget(self.deck_title)
        
        self.deck_description = QLabel("")
        info_layout.addWidget(self.deck_description)
        
        info_layout.addStretch()
        h_layout.addWidget(self.info_panel, 1)
        
        self.layout.addLayout(h_layout)
        
        # TODO: Populate deck list from available decks