from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
                            QPushButton, QListWidget, QListWidgetItem,
                            QLineEdit)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize

class EmptyStateWidget(QWidget):
    """Widget shown when there are no notes for the card"""
    
    createNoteClicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Create a large button for creating new notes
        create_button = QPushButton("Create New Note")
        create_button.setIcon(QIcon.fromTheme("document-new"))
        create_button.setIconSize(QSize(32, 32))
        create_button.setStyleSheet("""
            QPushButton {
                background-color: #4a86e8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 15px 30px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3a76d8;
            }
        """)
        create_button.clicked.connect(self.createNoteClicked.emit)
        
        layout.addStretch(1)
        layout.addWidget(create_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

class NotesListWidget(QWidget):
    """Widget displaying list of notes for a card"""
    
    noteSelected = pyqtSignal(QListWidgetItem)
    noteDoubleClicked = pyqtSignal(QListWidgetItem)
    createNoteClicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for the notes list"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Add a header with title
        header = QHBoxLayout()
        title_label = QLabel("Notes")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title_label)
        
        # Add search bar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search notes...")
        self.search_box.setMaximumWidth(200)
        header.addStretch()
        header.addWidget(self.search_box)
        
        layout.addLayout(header)
        
        # Create note list
        self.notes_list = QListWidget()
        self.notes_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e0f0ff;
                color: #000;
            }
        """)
        layout.addWidget(self.notes_list)
        
        # Bottom toolbar with actions
        actions_layout = QHBoxLayout()
        
        # Create New Note button
        new_button = QPushButton("New Note")
        new_button.setIcon(QIcon.fromTheme("document-new"))
        new_button.clicked.connect(self.createNoteClicked.emit)
        actions_layout.addWidget(new_button)
        
        self.manage_button = QPushButton("Manage")
        self.manage_button.setObjectName("manage_button")
        actions_layout.addWidget(self.manage_button)
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        
        # Connect signals
        self.notes_list.currentItemChanged.connect(lambda current, previous: 
                                                 self.noteSelected.emit(current) if current else None)
        self.notes_list.itemDoubleClicked.connect(self.noteDoubleClicked.emit)
        self.search_box.textChanged.connect(self.filter_notes)
    
    def add_note(self, name, file_path, card_id, select=False):
        """Add a note item to the list"""
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        item.setData(Qt.ItemDataRole.UserRole + 1, card_id)
        self.notes_list.insertItem(0, item)
        
        if select:
            self.notes_list.setCurrentItem(item)
        
        return item
    
    def clear_notes(self):
        """Clear all notes from the list"""
        self.notes_list.clear()
    
    def get_current_item(self):
        """Get the currently selected item"""
        return self.notes_list.currentItem()
    
    def filter_notes(self, text):
        """Filter notes based on search text"""
        search_text = text.lower()
        
        for i in range(self.notes_list.count()):
            item = self.notes_list.item(i)
            if not search_text or search_text in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
    
    def remove_item(self, item):
        """Remove an item from the list"""
        row = self.notes_list.row(item)
        self.notes_list.takeItem(row)