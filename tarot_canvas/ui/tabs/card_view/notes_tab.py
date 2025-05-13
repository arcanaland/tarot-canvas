from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
                           QPushButton, QInputDialog, QMessageBox, 
                           QFileDialog, QStackedWidget,
                           QMenu)
from PyQt6.QtGui import QIcon, QTextCursor, QAction
from PyQt6.QtCore import Qt, QSize, QTimer
import os
import time
import shutil
import re
from pathlib import Path

from tarot_canvas.ui.tabs.card_view.markdown_editor import MarkdownEditor
from tarot_canvas.ui.tabs.card_view.notes_list import NotesListWidget, EmptyStateWidget
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

class NotesTab(QWidget):
    """Tab for managing notes associated with a tarot card"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.current_card = None
        self.all_notes = {}  # Store info about all notes for linking
        self.current_file_path = None
        self.setup_ui()
        
        # Setup auto-save timer (save every 30 seconds)
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(30000)  # 30 seconds
    
    def setup_ui(self):
        """Set up the notes tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create stacked widget to switch between notes list and editor
        self.stack = QStackedWidget()
        
        # Create empty state widget for when there are no notes
        self.empty_state = EmptyStateWidget()
        self.empty_state.createNoteClicked.connect(self.create_new_note)
        
        # Create notes list widget
        self.notes_list_widget = NotesListWidget()
        self.notes_list_widget.createNoteClicked.connect(self.create_new_note)
        self.notes_list_widget.noteSelected.connect(self.on_note_selected)
        self.notes_list_widget.noteDoubleClicked.connect(self.open_note_editor)
        
        # Add menu to manage notes
        self.setup_manage_menu()
        
        # Create editor page
        self.editor_page = QWidget()
        editor_layout = QVBoxLayout(self.editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        
        # Editor header with back button and save button
        editor_header = QWidget()
        editor_header.setStyleSheet("""
            background-color: palette(window);
            border-bottom: 1px solid palette(mid);
        """)
        header_layout = QHBoxLayout(editor_header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        # Back button to return to list
        back_button = QPushButton()
        back_button.setIcon(QIcon.fromTheme("go-previous"))
        back_button.setToolTip("Back to note list")
        back_button.setMaximumSize(32, 32)
        back_button.clicked.connect(self.show_note_list)
        header_layout.addWidget(back_button)
        
        # Note title display
        self.note_title = QLabel()
        self.note_title.setStyleSheet("font-size: 16px; font-weight: bold; color: palette(text);")
        header_layout.addWidget(self.note_title)
        
        # Save button
        save_button = QPushButton()
        save_button.setIcon(QIcon.fromTheme("document-save"))
        save_button.setToolTip("Save note (Ctrl+S)")
        save_button.setMaximumSize(32, 32)
        save_button.clicked.connect(self.save_current_note)
        header_layout.addWidget(save_button)
        
        editor_layout.addWidget(editor_header)
        
        # Create enhanced markdown editor - no toolbar now
        self.note_editor = MarkdownEditor(self)
        self.note_editor.linkClicked.connect(self.handle_link_click)
        editor_layout.addWidget(self.note_editor)
        
        # Add widgets to stack
        self.stack.addWidget(self.empty_state)     # Index 0: Empty state
        self.stack.addWidget(self.notes_list_widget) # Index 1: Notes list
        self.stack.addWidget(self.editor_page)    # Index 2: Editor
        
        # Add stack to main layout
        layout.addWidget(self.stack)
    
    def setup_manage_menu(self):
        """Set up the manage menu for the notes list"""
        manage_menu = QMenu(self)
        
        rename_action = QAction("Rename Note", self)
        rename_action.triggered.connect(self.rename_current_note)
        manage_menu.addAction(rename_action)
        
        delete_action = QAction("Delete Note", self)
        delete_action.triggered.connect(self.delete_current_note)
        manage_menu.addAction(delete_action)
        
        export_action = QAction("Export Note", self)
        export_action.triggered.connect(self.export_current_note)
        manage_menu.addAction(export_action)
        
        self.notes_list_widget.manage_button.setMenu(manage_menu)
    
    def load_card_notes(self, card):
        """Load existing notes for a card"""
        self.current_card = card
        
        if not card:
            return
            
        card_id = card.get("id")
        if not card_id:
            return
        
        # Ensure deck manager reference is passed to editor
        if hasattr(self.parent_tab, 'deck_manager'):
            self.note_editor.set_deck_manager(self.parent_tab.deck_manager)
            logger.debug("Passed deck manager to editor")
        
        # Determine the notes directory path
        notes_dir = get_data_directory("tarot-canvas/notes") / card_id
        notes_dir = str(notes_dir)  # Convert Path to string for compatibility with existing code
        
        # Create the directory if it doesn't exist
        os.makedirs(notes_dir, exist_ok=True)
        
        # Load all notes at startup for linking
        self.load_all_notes()
        
        # Clear the current list
        self.notes_list_widget.clear_notes()
        
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
            # Parse the filename to get a display name
            display_name = self.get_display_name_from_filename(filename)
            self.notes_list_widget.add_note(display_name, file_path, card_id)
        
        # Show the appropriate view
        if not note_files:
            # Show empty state if no notes
            self.stack.setCurrentIndex(0)  # Empty state
        else:
            # Show notes list if there are notes
            self.stack.setCurrentIndex(1)  # Notes list
    
    def on_note_selected(self, item):
        """Handle selection of a note in the list"""
        if not item:
            # No item selected
            self.note_editor.clear()
            self.note_editor.setEnabled(False)
            self.current_file_path = None
            return
            
        # Auto-save any previously edited note
        if self.current_file_path and self.note_editor.document().isModified():
            self.save_note_to_file(self.current_file_path)
        
        # Get the file path from the item
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.current_file_path = file_path
    
    def open_note_editor(self, item):
        """Open the editor for the selected note"""
        if not item:
            return
            
        # Get the file path from the item
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.current_file_path = file_path
        
        # Set the note title
        self.note_title.setText(item.text())
        
        # Load the note content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set the content in the editor
            self.note_editor.setPlainText(content)
            self.note_editor.document().setModified(False)
            
            # Switch to editor page
            self.stack.setCurrentIndex(2)  # Editor page
            
            # Focus the editor
            self.note_editor.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load note: {e}")
    
    def show_note_list(self):
        """Return to the note list view"""
        # Save current note if modified
        if self.current_file_path and self.note_editor.document().isModified():
            self.save_note_to_file(self.current_file_path)
        
        # Show notes list or empty state based on whether there are notes
        if self.notes_list_widget.notes_list.count() > 0:
            self.stack.setCurrentIndex(1)  # Notes list
        else:
            self.stack.setCurrentIndex(0)  # Empty state
    
    def create_new_note(self):
        """Create a new note for the current card"""
        if not self.current_card:
            return
            
        card_id = self.current_card.get("id")
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
        notes_dir = get_data_directory("tarot-canvas/notes") / card_id
        notes_dir = str(notes_dir)
        try:
            os.makedirs(notes_dir, exist_ok=True)
            logger.info(f"Created/verified notes directory: {notes_dir}")
        except Exception as e:
            error_msg = f"Failed to create notes directory: {e}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
            return
        
        # Create the file
        file_path = str(Path(notes_dir) / filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# {name}\n\n")
            
            # Add to list and select it
            item = self.notes_list_widget.add_note(name, file_path, card_id, select=True)
            
            # Update all notes cache
            self.all_notes[name] = {
                'card_id': card_id,
                'file_path': file_path
            }
            
            # Open the editor with the new note
            self.open_note_editor(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create note: {e}")
    
    def delete_current_note(self):
        """Delete the currently selected note"""
        current_item = self.notes_list_widget.get_current_item()
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
            self.notes_list_widget.remove_item(current_item)
            
            # Remove from all notes cache
            for name, info in list(self.all_notes.items()):
                if info['file_path'] == file_path:
                    del self.all_notes[name]
                    break
            
            # Show empty state if no more notes
            if self.notes_list_widget.notes_list.count() == 0:
                self.stack.setCurrentIndex(0)  # Empty state
                self.current_file_path = None
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete note: {e}")
    
    def rename_current_note(self):
        """Rename the currently selected note"""
        current_item = self.notes_list_widget.get_current_item()
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
        
        new_file_path = str(Path(dirname) / new_filename)
        
        # Rename the file
        try:
            os.rename(file_path, new_file_path)
            
            # Update item
            current_item.setText(new_name)
            current_item.setData(Qt.ItemDataRole.UserRole, new_file_path)
            
            # Update all notes cache
            card_id = current_item.data(Qt.ItemDataRole.UserRole + 1)
            
            # Remove old entry
            for name, info in list(self.all_notes.items()):
                if info['file_path'] == file_path:
                    del self.all_notes[name]
                    break
                    
            # Add new entry
            self.all_notes[new_name] = {
                'card_id': card_id,
                'file_path': new_file_path
            }
            
            # Update current file path and title if this is the active note
            if self.current_file_path == file_path:
                self.current_file_path = new_file_path
                self.note_title.setText(new_name)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not rename note: {e}")
    
    def export_current_note(self):
        """Export the currently selected note to a file"""
        current_item = self.notes_list_widget.get_current_item()
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
    
    # Helper methods
    
    def load_all_notes(self):
        """Load information about all notes across all cards for linking"""
        self.all_notes = {}
        
        # Base notes directory
        base_dir = get_data_directory("tarot-canvas/notes")
        base_dir = str(base_dir)
        if not os.path.exists(base_dir):
            return
            
        # Loop through all card directories
        for card_dir in os.listdir(base_dir):
            card_path = os.path.join(base_dir, card_dir)
            if os.path.isdir(card_path):
                # Loop through all notes in this card directory
                for filename in os.listdir(card_path):
                    if filename.endswith(".md"):
                        file_path = os.path.join(card_path, filename)
                        display_name = self.get_display_name_from_filename(filename)
                        
                        # Store info about this note
                        self.all_notes[display_name] = {
                            'card_id': card_dir,
                            'file_path': file_path
                        }
    
    def get_display_name_from_filename(self, filename):
        """Extract a display name from a note filename"""
        # Remove extension
        name = filename.rsplit(".", 1)[0]
        
        # Remove timestamp prefix if it exists
        if "_" in name:
            parts = name.split("_", 1)
            if len(parts) > 1 and parts[0].isdigit():
                name = parts[1]
        
        # Replace underscores with spaces
        name = name.replace("_", " ")
        
        return name
    
    def get_link_suggestions(self):
        """Get suggestions for auto-completion when linking"""
        suggestions = []
        
        # Add all note names
        suggestions.extend(list(self.all_notes.keys()))
        
        # Add card references if deck manager is available
        if self.parent_tab and hasattr(self.parent_tab, 'deck_manager'):
            deck_manager = self.parent_tab.deck_manager
            
            # Add all cards from reference deck
            ref_deck = deck_manager.get_reference_deck()
            if ref_deck:
                # Use _cards directly or get_all_cards() if available
                cards = getattr(ref_deck, 'get_all_cards', lambda: ref_deck._cards)()
                for card in cards:
                    suggestions.append(f"card:{card['name']}")
            
            # Add all decks
            for deck in deck_manager.get_all_decks():
                suggestions.append(f"deck:{deck.get_name()}")
        
        return suggestions
    
    def save_current_note(self):
        """Save the current note content"""
        if not self.current_file_path:
            return
            
        self.save_note_to_file(self.current_file_path)
        self.note_editor.document().setModified(False)
    
    def save_note_to_file(self, file_path):
        """Save note content to a specific file"""
        content = self.note_editor.toPlainText()
        
        try:
            # Ensure the directory exists
            dir_path = os.path.dirname(file_path)
            os.makedirs(dir_path, exist_ok=True)
            
            # Log detailed info about save location and file
            logger.info(f"Saving note to: {file_path}")
            logger.info(f"Directory: {dir_path} exists: {os.path.exists(dir_path)}")
            logger.info(f"Content length: {len(content)} characters")
            
            # Save the file with explicit encoding
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                # Flush to disk to ensure it's written while file is still open
                f.flush()
                os.fsync(f.fileno())
            
            # Verify file was saved
            if os.path.exists(file_path):
                logger.info(f"File saved successfully: {os.path.getsize(file_path)} bytes")
            else:
                logger.error(f"File doesn't exist after save: {file_path}")
                    
            # Update modification time in file metadata
            os.utime(file_path, None)
            
            # Show temporary success message if main window is available
            from PyQt6.QtWidgets import QApplication
            main_window = QApplication.instance().activeWindow()
            if main_window and hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage("Note saved successfully", 3000)
                    
        except Exception as e:
            error_msg = f"Could not save note: {e}"
            logger.error(error_msg)
            # Add exception details and traceback
            import traceback
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Error", error_msg)
    
    # Link handling
    
    def handle_link_click(self, link_text):
        """Handle clicks on wiki links or markdown links"""
        if link_text.startswith("card:"):
            # Link to another card
            card_name = link_text[5:]
            self.navigate_to_card(card_name)
        elif link_text.startswith("deck:"):
            # Link to a deck
            deck_name = link_text[5:]
            self.navigate_to_deck(deck_name)
        else:
            # Assume it's a note link
            self.navigate_to_note(link_text)
    
    def navigate_to_card(self, card_name):
        """Navigate to a specific card by name"""
        if self.parent_tab and hasattr(self.parent_tab, 'deck_manager'):
            deck_manager = self.parent_tab.deck_manager
            ref_deck = deck_manager.get_reference_deck()
            
            if ref_deck:
                # Find the card by name
                cards = getattr(ref_deck, 'get_all_cards', lambda: ref_deck._cards)()
                for card in cards:
                    if card['name'].lower() == card_name.lower():
                        # Emit signal to navigate to this card
                        self.parent_tab.navigation_requested.emit("open_card_view", {
                            "card": card,
                            "deck": ref_deck
                        })
                        return
    
    def navigate_to_deck(self, deck_name):
        """Navigate to a specific deck by name"""
        if self.parent_tab and hasattr(self.parent_tab, 'deck_manager'):
            deck_manager = self.parent_tab.deck_manager
            
            # Find the deck by name
            for deck in deck_manager.get_all_decks():
                if deck.get_name().lower() == deck_name.lower():
                    # Emit signal to navigate to this deck
                    self.parent_tab.navigation_requested.emit("open_deck_view", {
                        "deck_path": deck.deck_path
                    })
                    return
    
    def navigate_to_note(self, note_name):
        """Navigate to a specific note by name"""
        # Check if the note exists in our cache
        if note_name in self.all_notes:
            note_info = self.all_notes[note_name]
            
            # If it's a note for a different card, navigate to that card first
            if self.current_card and note_info['card_id'] != self.current_card.get('id'):
                # Try to navigate to the card
                if self.parent_tab and hasattr(self.parent_tab, 'deck_manager'):
                    deck_manager = self.parent_tab.deck_manager
                    ref_deck = deck_manager.get_reference_deck()
                    
                    if ref_deck:
                        # Find the card by ID
                        cards = getattr(ref_deck, 'get_all_cards', lambda: ref_deck._cards)()
                        for card in cards:
                            if card['id'] == note_info['card_id']:
                                # Emit signal to navigate to this card
                                self.parent_tab.navigation_requested.emit("open_card_view", {
                                    "card": card,
                                    "deck": ref_deck,
                                    "open_note": note_name
                                })
                                return
            
            # If it's a note for the current card, just select it
            for i in range(self.notes_list_widget.notes_list.count()):
                item = self.notes_list_widget.notes_list.item(i)
                if item.text() == note_name:
                    self.notes_list_widget.notes_list.setCurrentItem(item)
                    self.open_note_editor(item)
                    return
    
    # Add this method to ensure saving when the tab is closed
    def closeEvent(self, event):
        """Save notes when tab is closed"""
        if self.current_file_path and self.note_editor.document().isModified():
            self.save_note_to_file(self.current_file_path)
        super().closeEvent(event)
    
    def auto_save(self):
        """Automatically save the current note if modified"""
        if self.current_file_path and self.note_editor.document().isModified():
            self.save_note_to_file(self.current_file_path)
            logger.debug(f"Auto-saved note: {self.current_file_path}")