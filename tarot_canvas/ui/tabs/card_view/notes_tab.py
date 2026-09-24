import os
import shutil
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.markdown_editor import MarkdownEditor
from tarot_canvas.ui.tabs.card_view.notes_list import EmptyStateWidget, NotesListWidget
from tarot_canvas.ui.tabs.card_view.notes_text import text
from tarot_canvas.utils.logger import logger


def renamed_path(file_path, new_name):
    """`file_path` under `new_name`, keeping the timestamp prefix as the note's id."""
    directory = os.path.dirname(file_path)
    stem = os.path.basename(file_path).rsplit(".", 1)[0]
    prefix = stem.split("_", 1)[0] if "_" in stem else stem
    timestamp = prefix if prefix.isdigit() else int(time.time())

    safe_name = new_name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    filename = f"{timestamp}_{safe_name}.md" if safe_name else f"{timestamp}.md"
    return str(Path(directory) / filename)


class NotesTab(QWidget):
    """Tab for managing notes associated with a tarot card"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.current_card = None
        self.notes_index = {}  # card_id -> [Note], the whole library
        self.all_notes = {}  # (card_id, path) -> Note, for linking
        self.current_file_path = None

        # A note the user asked for but hasn't written yet
        self.pending_path = None
        self.pending_card_id = None
        self.pending_name = ""
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

        # The note's name (editable)
        self.note_title = QLineEdit()
        self.note_title.setFrame(False)
        self.note_title.setPlaceholderText(text("name_placeholder"))
        apply_heading(self.note_title, SECTION_SCALE)
        self.note_title.editingFinished.connect(self.apply_title_edit)
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
        self.note_editor.document().contentsChanged.connect(self.on_editor_changed)
        editor_layout.addWidget(self.note_editor)

        # Add widgets to stack
        self.stack.addWidget(self.empty_state)  # Index 0: Empty state
        self.stack.addWidget(self.notes_list_widget)  # Index 1: Notes list
        self.stack.addWidget(self.editor_page)  # Index 2: Editor

        # Add stack to main layout
        layout.addWidget(self.stack)

    def setup_manage_menu(self):
        """Set up the manage menu for the notes list"""
        manage_menu = QMenu(self)

        rename_action = QAction(QIcon.fromTheme("edit-rename"), "Rename Note", self)
        rename_action.triggered.connect(self.rename_current_note)
        manage_menu.addAction(rename_action)

        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Delete Note", self)
        delete_action.triggered.connect(self.delete_current_note)
        manage_menu.addAction(delete_action)

        export_action = QAction(QIcon.fromTheme("document-export"), "Export Note", self)
        export_action.triggered.connect(self.export_current_note)
        manage_menu.addAction(export_action)

        self.notes_list_widget.manage_button.setMenu(manage_menu)

    def load_card_notes(self, card):
        """Load existing notes for a card"""
        self.discard_pending_note()

        # Stepping to another card mustn't leave an edit waiting on the autosave timer
        self.save_if_modified()

        self.current_card = card

        if not card:
            return

        card_id = card.get("id")
        if not card_id:
            return

        # Ensure deck manager reference is passed to editor
        if hasattr(self.parent_tab, "deck_manager"):
            self.note_editor.set_deck_manager(self.parent_tab.deck_manager)
            logger.debug("Passed deck manager to editor")

        # The directory is made when the first note is written, not when a card is opened
        self.load_all_notes()

        # Clear the current list
        self.notes_list_widget.clear_notes()

        card_notes = self.notes_index.get(card_id, [])
        for note in card_notes:
            self.notes_list_widget.add_note(notes_model.label(note), str(note.path), card_id)

        # Show notes list if there are notes, empty state otherwise
        self.stack.setCurrentIndex(1 if card_notes else 0)

    def on_note_selected(self, item):
        """Handle selection of a note in the list"""
        self.discard_pending_note()

        if not item:
            # No item selected
            self.note_editor.clear()
            self.note_editor.setEnabled(False)
            self.current_file_path = None
            return

        # Auto-save any previously edited note
        self.save_if_modified()

        # Get the file path from the item
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.current_file_path = file_path

    def open_note_editor(self, item):
        """Open the editor for the selected note"""
        self.discard_pending_note()

        if not item:
            return

        # Get the file path from the item
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.current_file_path = file_path

        # The field is the note's name. For a nameless note the row is labelled by its
        # first line, which is content — putting that in the name field would offer to
        # rename the note to its own text.
        self.note_title.setText(notes_model.display_name_from_filename(os.path.basename(file_path)))

        # Load the note content
        try:
            with open(file_path, encoding="utf-8") as f:
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

    def apply_title_edit(self):
        """Rename the open note to whatever the header now says."""
        new_name = self.note_title.text().strip()

        if self.pending_path:
            # No file to rename yet; the name is held for whoever creates it
            self.pending_name = new_name
            return

        if not self.current_file_path:
            return

        current = notes_model.display_name_from_filename(os.path.basename(self.current_file_path))
        if new_name == current:
            return

        self.rename_note_to(self.current_file_path, new_name)

    def rename_note_to(self, file_path, new_name):
        """Rename a note's file and bring every view of it up to date."""
        new_file_path = renamed_path(file_path, new_name)
        if new_file_path == file_path:
            return None

        try:
            os.rename(file_path, new_file_path)
        except OSError as error:
            QMessageBox.critical(self, "Error", f"Could not rename note: {error}")
            return None

        item = self.item_for_path(file_path)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, new_file_path)

        if self.current_file_path == file_path:
            self.current_file_path = new_file_path

        self.load_all_notes()

        if item is not None:
            note = self.all_notes.get((self.pending_card_id or self.card_id(), new_file_path))
            item.setText(notes_model.label(note) if note else new_name)

        note_events().notes_changed.emit()
        return new_file_path

    def card_id(self):
        return self.current_card.get("id") if self.current_card else None

    def item_for_path(self, file_path):
        """The list row holding `file_path`, or None if this card isn't showing it."""
        listing = self.notes_list_widget.notes_list
        for index in range(listing.count()):
            item = listing.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                return item
        return None

    def open_note_path(self, file_path):
        item = self.item_for_path(file_path)
        if item is not None:
            self.notes_list_widget.notes_list.setCurrentItem(item)
            self.open_note_editor(item)

    def show_note_list(self):
        """Return to the note list view"""
        self.discard_pending_note()

        self.save_if_modified()

        # Show notes list or empty state based on whether there are notes
        if self.notes_list_widget.notes_list.count() > 0:
            self.stack.setCurrentIndex(1)  # Notes list
        else:
            self.stack.setCurrentIndex(0)  # Empty state

    def create_new_note(self):
        """Open the editor on a note that doesn't exist yet."""
        if not self.current_card:
            return

        card_id = self.current_card.get("id")
        if not card_id:
            return

        # save whatever is open
        self.save_if_modified()

        self.current_file_path = None
        self.pending_card_id = card_id
        self.pending_name = ""
        self.pending_path = str(notes_model.notes_base() / card_id / f"{int(time.time())}.md")

        self.note_title.setText("")
        self.note_editor.clear()
        self.note_editor.setEnabled(True)
        self.note_editor.document().setModified(False)

        self.stack.setCurrentIndex(2)  # Editor page
        self.note_editor.setFocus()

    def discard_pending_note(self):
        """Forget a note that was asked for but never written."""
        self.pending_path = None
        self.pending_card_id = None

    def on_editor_changed(self):
        """Realise a pending note, and keep an unnamed one's row label honest."""
        self.write_pending_note()
        self.sync_unnamed_row_label()

    def sync_unnamed_row_label(self):
        if not self.current_file_path:
            return

        if not Path(self.current_file_path).stem.isdigit():
            return

        item = self.notes_list_widget.get_current_item()
        if item is None or item.data(Qt.ItemDataRole.UserRole) != self.current_file_path:
            return

        item.setText(notes_model.first_line_of(self.note_editor.toPlainText()))

    def write_pending_note(self):
        """Give a pending note a file."""
        if not self.pending_path or not self.note_editor.toPlainText().strip():
            return

        # A name typed into the header before anything was written belongs in the
        # filename the note is about to get, not in a rename straight after it
        file_path = renamed_path(self.pending_path, self.pending_name)
        card_id = self.pending_card_id

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        except OSError as error:
            error_msg = f"Failed to create notes directory: {error}"
            logger.error(error_msg)
            QMessageBox.critical(self, "Error", error_msg)
            return

        self.pending_path = None
        self.pending_card_id = None
        self.current_file_path = file_path

        # This both writes the file and re-reads the index that now includes it
        self.save_note_to_file(file_path)
        self.note_editor.document().setModified(False)

        note = self.all_notes.get((card_id, file_path))
        label = notes_model.label(note) if note else ""
        self.notes_list_widget.add_note(label, file_path, card_id, select=True)

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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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
            self.load_all_notes()
            note_events().notes_changed.emit()

            # Show empty state if no more notes
            if self.notes_list_widget.notes_list.count() == 0:
                self.stack.setCurrentIndex(0)  # Empty state
                self.current_file_path = None
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete note: {e}")

    def rename_current_note(self):
        """Rename the selected note from the manage menu."""
        current_item = self.notes_list_widget.get_current_item()
        if not current_item:
            return

        file_path = current_item.data(Qt.ItemDataRole.UserRole)
        current_name = notes_model.display_name_from_filename(os.path.basename(file_path))

        new_name, ok = QInputDialog.getText(
            self, "Rename Note", "Enter a new name for this note:", text=current_name
        )

        if not ok or new_name == current_name:
            return

        if self.rename_note_to(file_path, new_name) and self.current_file_path == renamed_path(
            file_path, new_name
        ):
            self.note_title.setText(new_name)

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
            "Markdown Files (*.md);;All Files (*)",
        )

        if not export_path:
            return

        # Copy the file
        try:
            shutil.copy2(file_path, export_path)

            # Show success message
            QMessageBox.information(self, "Export Successful", f"Note exported to {export_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not export note: {e}")

    # Helper methods

    def load_all_notes(self):
        """Re-read every note in the library, for linking"""
        self.notes_index = notes_model.scan()
        self.all_notes = {
            (note.card_id, str(note.path)): note
            for notes in self.notes_index.values()
            for note in notes
        }

    def get_link_suggestions(self):
        """Get suggestions for auto-completion when linking"""
        suggestions = []

        # Add all note names, first occurrence wins so the order is stable
        seen = set()
        for note in self.all_notes.values():
            if note.title and note.title not in seen:
                seen.add(note.title)
                suggestions.append(note.title)

        # Add card references if deck manager is available
        if self.parent_tab and hasattr(self.parent_tab, "deck_manager"):
            deck_manager = self.parent_tab.deck_manager

            # Add all cards from reference deck
            ref_deck = deck_manager.get_reference_deck()
            if ref_deck:
                # Use _cards directly or get_all_cards() if available
                cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
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

    def save_if_modified(self):
        """Persist the open note if it has unsaved edits."""
        if self.current_file_path and self.note_editor.document().isModified():
            self.save_note_to_file(self.current_file_path)
            self.note_editor.document().setModified(False)
            return True
        return False

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
            with open(file_path, "w", encoding="utf-8") as f:
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

            self.load_all_notes()
            note_events().notes_changed.emit()

            # Show temporary success message if main window is available
            from PyQt6.QtWidgets import QApplication

            main_window = QApplication.instance().activeWindow()
            if main_window and hasattr(main_window, "statusBar"):
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
        if self.parent_tab and hasattr(self.parent_tab, "deck_manager"):
            deck_manager = self.parent_tab.deck_manager
            ref_deck = deck_manager.get_reference_deck()

            if ref_deck:
                # Find the card by name
                cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
                for card in cards:
                    if card["name"].lower() == card_name.lower():
                        # Emit signal to navigate to this card
                        self.parent_tab.navigation_requested.emit(
                            "open_card_view", {"card": card, "deck": ref_deck}
                        )
                        return

    def navigate_to_deck(self, deck_name):
        """Navigate to a specific deck by name"""
        if self.parent_tab and hasattr(self.parent_tab, "deck_manager"):
            deck_manager = self.parent_tab.deck_manager

            # Find the deck by name
            for deck in deck_manager.get_all_decks():
                if deck.get_name().lower() == deck_name.lower():
                    # Emit signal to navigate to this deck
                    self.parent_tab.navigation_requested.emit(
                        "open_deck_view", {"deck_path": deck.deck_path}
                    )
                    return

    def find_note_by_title(self, note_name):
        """A title is not unique across cards: prefer this card's, then the newest.

        An empty needle matches nothing: every unnamed note has title "", so `[[]]` would
        otherwise resolve to all of them at once.
        """
        if not note_name:
            return None

        matches = [note for note in self.all_notes.values() if note.title == note_name]
        if not matches:
            return None

        if self.current_card:
            card_id = self.current_card.get("id")
            here = [note for note in matches if note.card_id == card_id]
            if here:
                return max(here, key=lambda note: note.modified)

        return max(matches, key=lambda note: note.modified)

    def navigate_to_note(self, note_name):
        """Navigate to a specific note by name"""
        note_info = self.find_note_by_title(note_name)
        if note_info:
            # If it's a note for a different card, navigate to that card first
            if (
                self.current_card
                and note_info.card_id != self.current_card.get("id")
                and self.parent_tab
                and hasattr(self.parent_tab, "deck_manager")
            ):
                deck_manager = self.parent_tab.deck_manager
                ref_deck = deck_manager.get_reference_deck()

                if ref_deck:
                    # Find the card by ID
                    cards = getattr(ref_deck, "get_all_cards", lambda: ref_deck._cards)()
                    for card in cards:
                        if card["id"] == note_info.card_id:
                            # Emit signal to navigate to this card
                            self.parent_tab.navigation_requested.emit(
                                "open_card_view",
                                {"card": card, "deck": ref_deck, "open_note": note_name},
                            )
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
        self.save_if_modified()
        super().closeEvent(event)

    def auto_save(self):
        """Automatically save the current note if modified"""
        path = self.current_file_path
        if self.save_if_modified():
            logger.debug(f"Auto-saved note: {path}")
