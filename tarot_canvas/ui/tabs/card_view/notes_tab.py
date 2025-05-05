from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
                           QPushButton, QListWidget, QListWidgetItem,
                           QStackedWidget, QPlainTextEdit, QInputDialog, 
                           QMessageBox, QFileDialog, QTextBrowser, 
                           QApplication, QSplitter)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import os
import time
import shutil
import re

class NotesTab(QWidget):
    """Tab for managing notes associated with a tarot card"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the notes tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove unnecessary margins
        
        # Splitter for note list and content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT PANEL - List of notes with compact controls
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(10, 10, 5, 10)
        
        # Notes list with add button in a toolbar-like layout
        list_header = QHBoxLayout()
        list_header.setContentsMargins(0, 0, 0, 5)
        
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("font-weight: bold;")
        list_header.addWidget(notes_label)
        
        list_header.addStretch()
        
        # Create a small, icon-only add button
        add_button = QPushButton()
        add_button.setIcon(QIcon.fromTheme("list-add"))
        add_button.setToolTip("Create new note")
        add_button.setMaximumSize(24, 24)
        add_button.clicked.connect(self.create_new_note)
        list_header.addWidget(add_button)
        
        list_layout.addLayout(list_header)
        
        # Add the list widget
        self.notes_list = QListWidget()
        self.notes_list.setMinimumWidth(120)
        self.notes_list.currentItemChanged.connect(self.on_note_selected)
        list_layout.addWidget(self.notes_list)
        
        # Add compact button row below the list
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 5, 0, 0)
        button_row.setSpacing(2)  # Tighter spacing for a compact look
        
        # Small icon buttons for note operations
        delete_button = QPushButton()
        delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        delete_button.setToolTip("Delete selected note")
        delete_button.setMaximumSize(24, 24)
        delete_button.clicked.connect(self.delete_current_note)
        button_row.addWidget(delete_button)
        
        rename_button = QPushButton()
        rename_button.setIcon(QIcon.fromTheme("edit-rename"))
        rename_button.setToolTip("Rename selected note")
        rename_button.setMaximumSize(24, 24)
        rename_button.clicked.connect(self.rename_current_note)
        button_row.addWidget(rename_button)
        
        export_button = QPushButton()
        export_button.setIcon(QIcon.fromTheme("document-export"))
        export_button.setToolTip("Export selected note")
        export_button.setMaximumSize(24, 24)
        export_button.clicked.connect(self.export_current_note)
        button_row.addWidget(export_button)
        
        button_row.addStretch()
        list_layout.addLayout(button_row)
        
        # Add list panel to splitter
        splitter.addWidget(list_panel)
        
        # RIGHT PANEL - Note editor/viewer
        note_panel = QWidget()
        note_layout = QVBoxLayout(note_panel)
        note_layout.setContentsMargins(5, 10, 10, 10)
        
        # Stack for edit/preview modes
        self.note_stack = QStackedWidget()
        
        # Edit widget with markdown editor
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        
        self.note_editor = QPlainTextEdit()
        self.note_editor.setPlaceholderText("Write your notes here using Markdown...\n\n# Heading\n\n**Bold text**\n\n- List item")
        edit_layout.addWidget(self.note_editor)
        self.note_stack.addWidget(edit_widget)
        
        # Preview widget with markdown rendering
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.note_preview = QTextBrowser()
        self.note_preview.setOpenExternalLinks(True)
        preview_layout.addWidget(self.note_preview)
        self.note_stack.addWidget(preview_widget)
        
        note_layout.addWidget(self.note_stack)
        
        # Clean footer with minimal controls
        footer_bar = QHBoxLayout()
        footer_bar.setContentsMargins(0, 5, 0, 0)
        
        # Toggle Preview/Edit
        self.preview_button = QPushButton()
        self.preview_button.setCheckable(True)
        self.preview_button.setIcon(QIcon.fromTheme("document-preview"))
        self.preview_button.setToolTip("Toggle preview mode")
        self.preview_button.toggled.connect(self.toggle_preview_mode)
        footer_bar.addWidget(self.preview_button)
        
        footer_bar.addStretch()
        
        # Save button aligned right
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolTip("Save note")
        self.save_button.clicked.connect(self.save_current_note)
        footer_bar.addWidget(self.save_button)
        
        note_layout.addLayout(footer_bar)
        
        # Add note panel to splitter
        splitter.addWidget(note_panel)
        
        # Set initial splitter sizes (30% list, 70% editor)
        splitter.setSizes([300, 700])
        
        # Add the splitter to the main layout
        layout.addWidget(splitter)
    
    def load_card_notes(self, card):
        """Load existing notes for a card"""
        if not card:
            return
            
        card_id = card.get("id")
        if not card_id:
            return
        
        # Determine the notes directory path
        notes_dir = os.path.expanduser(f"~/.local/share/tarot-canvas/notes/{card_id}")
        
        # Create the directory if it doesn't exist
        os.makedirs(notes_dir, exist_ok=True)
        
        # Clear the current list
        self.notes_list.clear()
        
        # Load all markdown files in the directory
        note_files = []
        if os.path.exists(notes_dir):
            for filename in os.listdir(notes_dir):
                if filename.endswith(".md"):
                    file_path = os.path.join(notes_dir, filename)
                    # Get file stats
                    stats = os.stat(file_path)
                    # Save tuple of (modified time, filename, full path)
                    note_files.append((stats.st_mtime, filename, file_path))
        
        # Sort by modified time (newest first)
        note_files.sort(reverse=True)
        
        # Add to list widget
        for _, filename, file_path in note_files:
            # Parse the filename to get a nice display name
            display_name = filename
            if "_" in filename:
                # Remove timestamp prefix and extension
                parts = filename.split("_", 1)
                if len(parts) > 1:
                    display_name = parts[1].rsplit(".", 1)[0]
            
            # Create the item
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.notes_list.addItem(item)
        
        # Select the first note if available
        if self.notes_list.count() > 0:
            self.notes_list.setCurrentRow(0)
        else:
            # No notes yet, disable the editor
            self.note_editor.setEnabled(False)
            self.save_button.setEnabled(False)
            self.preview_button.setEnabled(False)
    
    def on_note_selected(self, current, previous):
        """Handle selection of a note in the list"""
        if not current:
            # Clear and disable the editor
            self.note_editor.clear()
            self.note_editor.setEnabled(False)
            self.save_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            return
        
        # Get the file path from the item
        file_path = current.data(Qt.ItemDataRole.UserRole)
        
        # Load the note content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set the content in the editor
            self.note_editor.setPlainText(content)
            
            # Also update the preview if in preview mode
            if self.preview_button.isChecked():
                self.update_preview()
            
            # Enable editor and buttons
            self.note_editor.setEnabled(True)
            self.save_button.setEnabled(True)
            self.preview_button.setEnabled(True)
        except Exception as e:
            print(f"Error loading note: {e}")
            self.note_editor.setPlainText(f"Error loading note: {e}")
    
    def create_new_note(self):
        """Create a new note for the current card"""
        if not self.parent_tab or not self.parent_tab.card:
            return
            
        card_id = self.parent_tab.card.get("id")
        if not card_id:
            return
        
        # Get a name for the new note
        name, ok = QInputDialog.getText(
            self, 
            "New Note", 
            "Enter a name for this note:",
            text="Untitled Note"
        )
        
        if not ok or not name:
            return
        
        # Generate filename with timestamp
        timestamp = int(time.time())
        safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        filename = f"{timestamp}_{safe_name}.md"
        
        # Create notes directory if it doesn't exist
        notes_dir = os.path.expanduser(f"~/.local/share/tarot-canvas/notes/{card_id}")
        os.makedirs(notes_dir, exist_ok=True)
        
        # Create the file
        file_path = os.path.join(notes_dir, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {name}\n\n")
            
            # Add to list
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.notes_list.insertItem(0, item)
            self.notes_list.setCurrentItem(item)
            
            # Focus the editor
            self.note_editor.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create note: {e}")
    
    def save_current_note(self):
        """Save the current note content"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        content = self.note_editor.toPlainText()
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Update the preview if in preview mode
            if self.preview_button.isChecked():
                self.update_preview()
            
            # Show temporary success message
            status_bar = QApplication.instance().activeWindow().statusBar()
            if status_bar:
                status_bar.showMessage("Note saved successfully", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save note: {e}")
    
    def toggle_preview_mode(self, checked):
        """Toggle between edit and preview modes"""
        if checked:
            # Switch to preview mode
            self.update_preview()
            self.note_stack.setCurrentIndex(1)
            self.preview_button.setText("Edit")
        else:
            # Switch to edit mode
            self.note_stack.setCurrentIndex(0)
            self.preview_button.setText("Preview")
    
    def update_preview(self):
        """Update the preview with rendered markdown"""
        content = self.note_editor.toPlainText()
        
        # Simple markdown to HTML conversion
        html = self.simple_markdown_to_html(content)
        
        # Set the HTML in the preview
        self.note_preview.setHtml(html)
    
    def simple_markdown_to_html(self, markdown):
        """Convert markdown to HTML (simplified version)"""
        # For a proper implementation, use a library like Python-Markdown
        # This is a very simplified version that handles basic formatting
        
        html = markdown
        
        # Headers
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # Lists
        html = re.sub(r'^- (.+)$', r'<ul><li>\1</li></ul>', html, flags=re.MULTILINE)
        
        # Links
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        
        # Paragraphs
        html = re.sub(r'(?<!\n)\n(?!\n)(.+)', r'<br>\1', html)
        html = re.sub(r'\n\n(.+)', r'<p>\1</p>', html)
        
        return html
    
    def delete_current_note(self):
        """Delete the currently selected note"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Note",
            f"Are you sure you want to delete the note '{current_item.text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Get the file path
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Delete the file
        try:
            os.remove(file_path)
            
            # Remove from list
            row = self.notes_list.row(current_item)
            self.notes_list.takeItem(row)
            
            # If there are no more notes, disable the editor
            if self.notes_list.count() == 0:
                self.note_editor.clear()
                self.note_editor.setEnabled(False)
                self.save_button.setEnabled(False)
                self.preview_button.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete note: {e}")
    
    def rename_current_note(self):
        """Rename the currently selected note"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Get current name
        current_name = current_item.text()
        
        # Ask for new name
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Note",
            "Enter a new name for this note:",
            text=current_name
        )
        
        if not ok or not new_name or new_name == current_name:
            return
        
        # Get the file path
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Generate new filename
        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Keep the timestamp prefix if it exists
        if "_" in filename:
            timestamp = filename.split("_", 1)[0]
            safe_name = new_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            new_filename = f"{timestamp}_{safe_name}.md"
        else:
            # If no timestamp, add one
            timestamp = int(time.time())
            safe_name = new_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            new_filename = f"{timestamp}_{safe_name}.md"
        
        new_file_path = os.path.join(dirname, new_filename)
        
        # Rename the file
        try:
            os.rename(file_path, new_file_path)
            
            # Update item
            current_item.setText(new_name)
            current_item.setData(Qt.ItemDataRole.UserRole, new_file_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not rename note: {e}")
    
    def export_current_note(self):
        """Export the currently selected note to a file"""
        current_item = self.notes_list.currentItem()
        if not current_item:
            return
        
        # Get the file path
        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Ask for export location
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Note",
            os.path.expanduser(f"~/Documents/{current_item.text()}.md"),
            "Markdown Files (*.md);;All Files (*)"
        )
        
        if not export_path:
            return
        
        # Copy the file
        try:
            shutil.copy2(file_path, export_path)
            
            # Show success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"Note exported to {export_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not export note: {e}")