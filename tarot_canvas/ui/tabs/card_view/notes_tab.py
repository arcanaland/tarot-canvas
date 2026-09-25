import os
import shutil
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_model import NoteRole, NotesListModel
from tarot_canvas.ui.notes_text import text
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.markdown_editor import MarkdownEditor
from tarot_canvas.ui.tabs.card_view.notes_list import NotesEmptyPage, NotesListPage
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.utils.logger import logger

# A deleted note is renamed under this suffix until the delete is committed.
STAGED_DELETE_SUFFIX = ".deleted"


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

        # (original path, staged path) of a delete that can still be undone
        self.staged_delete = None
        # The note a menu was opened on; see action_target
        self.menu_target = None

        self.setup_actions()
        self.setup_ui()

        # Setup auto-save timer (save every 30 seconds)
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(30000)  # 30 seconds

        # Closing the window closes no tab, so quitting is the last chance to commit
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.commit_pending_delete)

    def setup_actions(self):
        """One set of actions, shown on the row, in its context menu and in the editor."""
        self.open_action = QAction(QIcon.fromTheme("document-open"), text("open"), self)
        self.open_action.triggered.connect(self.open_target)

        self.rename_action = QAction(QIcon.fromTheme("edit-rename"), text("rename"), self)
        self.rename_action.triggered.connect(self.rename_target)

        self.export_action = QAction(QIcon.fromTheme("document-export"), text("export"), self)
        self.export_action.triggered.connect(self.export_target)

        self.delete_action = QAction(QIcon.fromTheme("edit-delete"), text("delete"), self)
        self.delete_action.triggered.connect(self.delete_target)

        self.rename_action.setShortcut(QKeySequence(Qt.Key.Key_F2))
        self.delete_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
        for action in (self.rename_action, self.delete_action):
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self.note_menu = QMenu(self)
        self.note_menu.addActions(
            [self.open_action, self.rename_action, self.export_action, self.delete_action]
        )

        # The note is already open there
        self.editor_menu = QMenu(self)
        self.editor_menu.addActions([self.rename_action, self.export_action, self.delete_action])
        self.editor_menu.aboutToShow.connect(self.target_open_note)

        for menu in (self.note_menu, self.editor_menu):
            # A menu hides before it triggers the chosen action, so the target is
            # forgotten only once that action has run
            menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self.forget_menu_target))

        self.new_note_action = QAction(QIcon.fromTheme("document-new"), text("create_note"), self)
        self.new_note_action.setToolTip(text("new_note_tooltip"))
        self.new_note_action.triggered.connect(self.create_new_note)

        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), text("undo"), self)
        self.undo_action.triggered.connect(self.undo_delete)

    def setup_ui(self):
        """Set up the notes tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Hidden, it takes no room, margins included
        message_row = QVBoxLayout()
        margin = units.LARGE_SPACING
        message_row.setContentsMargins(margin, margin, margin, 0)
        self.message = InlineMessage(close_text=text("dismiss"))
        self.message.dismissed.connect(self.commit_pending_delete)
        message_row.addWidget(self.message)
        layout.addLayout(message_row)

        # Create stacked widget to switch between notes list and editor
        self.stack = QStackedWidget()

        self.empty_page = NotesEmptyPage(self.new_note_action)

        self.list_model = NotesListModel(
            parent=self, card_in_subtitle=False, editable=True, stub_preview=text("stub_note")
        )
        # Queued: the rename rescans and resets the model the editor is committing to
        self.list_model.renameRequested.connect(
            self.rename_note_to, Qt.ConnectionType.QueuedConnection
        )
        self.row_delegate = NoteRowDelegate(
            self, thumbnail=False, menu_button=True, menu_tooltip=text("note_menu_tooltip")
        )
        self.row_delegate.menuRequested.connect(
            lambda index, pos: self.show_note_menu(self.path_at(index), pos)
        )

        self.list_page = NotesListPage(self.list_model, self.row_delegate, self.new_note_action)
        self.list_view = self.list_page.view
        self.list_view.activated.connect(lambda index: self.open_note_editor(self.path_at(index)))
        self.list_view.customContextMenuRequested.connect(self.on_list_context_menu)
        self.list_view.addActions([self.rename_action, self.delete_action])

        # Create editor page
        self.editor_page = QWidget()
        editor_layout = QVBoxLayout(self.editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Editor header with back button and save button
        editor_header = QWidget()
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
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolTip("Save note (Ctrl+S)")
        self.save_button.setMaximumSize(32, 32)
        self.save_button.clicked.connect(self.save_current_note)
        header_layout.addWidget(self.save_button)

        self.editor_menu_button = QToolButton()
        self.editor_menu_button.setIcon(QIcon.fromTheme("overflow-menu"))
        self.editor_menu_button.setToolTip(text("note_menu_tooltip"))
        self.editor_menu_button.setAutoRaise(True)
        self.editor_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.editor_menu_button.setMenu(self.editor_menu)
        header_layout.addWidget(self.editor_menu_button)

        editor_layout.addWidget(editor_header)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        editor_layout.addWidget(separator)

        # Create enhanced markdown editor - no toolbar now
        self.note_editor = MarkdownEditor(self)
        self.note_editor.linkClicked.connect(self.handle_link_click)
        self.note_editor.document().contentsChanged.connect(self.write_pending_note)
        # A save says nothing; Save greys out instead
        self.save_button.setEnabled(False)
        self.note_editor.document().modificationChanged.connect(self.save_button.setEnabled)
        editor_layout.addWidget(self.note_editor)

        # Add widgets to stack
        self.stack.addWidget(self.empty_page)  # Index 0: Empty state
        self.stack.addWidget(self.list_page)  # Index 1: Notes list
        self.stack.addWidget(self.editor_page)  # Index 2: Editor

        # Add stack to main layout
        layout.addWidget(self.stack)

    def load_card_notes(self, card):
        """Load existing notes for a card"""
        self.discard_pending_note()

        # Stepping to another card hides the Undo, so the delete it offered is final
        self.commit_pending_delete()

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
        self.current_file_path = None
        self.refresh_list()
        self.show_list_or_empty_page()

    # -- the list -----------------------------------------------------------

    def refresh_list(self):
        """Re-read the index and show this card's notes, keeping the open note selected."""
        self.load_all_notes()

        card_id = self.card_id()
        self.list_model.set_card_notes(card_id, self.notes_index.get(card_id, []))
        self.select_path(self.current_file_path)

        if self.stack.currentWidget() is not self.editor_page:
            self.show_list_or_empty_page()

    def show_list_or_empty_page(self):
        has_notes = self.list_model.rowCount() > 0
        self.stack.setCurrentWidget(self.list_page if has_notes else self.empty_page)

    def select_path(self, file_path):
        """Select the row holding `file_path`, and return its index; invalid if it isn't listed."""
        index = self.list_model.index_for_path(file_path)
        if index.isValid():
            self.list_view.setCurrentIndex(index)
        return index

    def path_at(self, index):
        note = index.data(NoteRole) if index.isValid() else None
        return str(note.path) if note else None

    def note_at(self, file_path):
        return self.all_notes.get((self.card_id(), file_path))

    # -- the actions --------------------------------------------------------

    def show_note_menu(self, file_path, global_pos):
        if not file_path:
            return
        self.menu_target = file_path
        self.note_menu.popup(global_pos)

    def on_list_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if index.isValid():
            self.show_note_menu(self.path_at(index), self.list_view.viewport().mapToGlobal(pos))

    def target_open_note(self):
        self.menu_target = self.current_file_path

    def forget_menu_target(self):
        self.menu_target = None

    def action_target(self):
        """The note an action acts on."""
        if self.menu_target:
            return self.menu_target
        return self.path_at(self.list_view.currentIndex())

    def open_target(self):
        self.open_note_path(self.action_target())

    def rename_target(self):
        if self.stack.currentWidget() is self.editor_page:
            self.note_title.setFocus()
            self.note_title.selectAll()
            return

        index = self.select_path(self.action_target())
        if index.isValid():
            self.list_view.edit(index)

    def export_target(self):
        file_path = self.action_target()
        if file_path:
            self.export_note(file_path)

    def delete_target(self):
        file_path = self.action_target()
        if file_path:
            self.delete_note(file_path)

    # -- opening and renaming -------------------------------------------------

    def open_note_editor(self, file_path):
        """Open the editor on a note"""
        self.discard_pending_note()

        if not file_path:
            return

        # Auto-save any previously edited note
        self.save_if_modified()

        self.current_file_path = file_path

        # note's name. For nameless notes, the row is labelled by its first line
        self.note_title.setText(notes_model.display_name_from_filename(os.path.basename(file_path)))

        # Load the note content
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Set the content in the editor
            self.note_editor.setPlainText(content)
            self.note_editor.setEnabled(True)
            self.note_editor.document().setModified(False)

            # Switch to editor page
            self.stack.setCurrentWidget(self.editor_page)

            # Focus the editor
            self.note_editor.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load note: {e}")

    def apply_title_edit(self):
        """Rename the open note to whatever the header now says."""
        new_name = self.note_title.text().strip()

        if self.pending_path:
            # No file to rename yet
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

        if self.current_file_path == file_path:
            self.current_file_path = new_file_path

        self.refresh_list()
        note_events().notes_changed.emit()
        return new_file_path

    def card_id(self):
        return self.current_card.get("id") if self.current_card else None

    def open_note_path(self, file_path):
        if self.select_path(file_path).isValid():
            self.open_note_editor(file_path)

    def show_note_list(self):
        """Return to the note list view"""
        self.discard_pending_note()

        self.save_if_modified()

        # Rows may have been written, named or retitled while the list was hidden
        self.refresh_list()
        self.show_list_or_empty_page()

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

        self.stack.setCurrentWidget(self.editor_page)
        self.note_editor.setFocus()

    def discard_pending_note(self):
        """Forget a note that was asked for but never written."""
        self.pending_path = None
        self.pending_card_id = None

    def write_pending_note(self):
        """Give a pending note a file."""
        if not self.pending_path or not self.note_editor.toPlainText().strip():
            return

        file_path = renamed_path(self.pending_path, self.pending_name)

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

    # -- deleting, undoably ---------------------------------------------------

    def delete_note(self, file_path):
        """Take the note out of every view now; remove the file once Undo is gone."""
        # One Undo at a time: the delete it offered becomes final
        self.commit_pending_delete()

        if self.current_file_path == file_path:
            # What Undo brings back is the note as last typed
            self.save_if_modified()
            self.current_file_path = None

        staged_path = file_path + STAGED_DELETE_SUFFIX
        try:
            os.rename(file_path, staged_path)
        except OSError as error:
            QMessageBox.critical(self, "Error", f"Could not delete note: {error}")
            return

        self.staged_delete = (file_path, staged_path)
        self.show_note_list()
        note_events().notes_changed.emit()
        self.message.show_message(text("deleted_message"), [self.undo_action])

    def undo_delete(self):
        if not self.staged_delete:
            return

        file_path, staged_path = self.staged_delete
        self.staged_delete = None
        self.message.hide()

        try:
            os.rename(staged_path, file_path)
        except OSError as error:
            QMessageBox.critical(self, "Error", f"Could not restore note: {error}")
            return

        self.refresh_list()
        note_events().notes_changed.emit()

    @pyqtSlot()
    def commit_pending_delete(self):
        """Make the staged delete final."""
        if not self.staged_delete:
            return

        _file_path, staged_path = self.staged_delete
        self.staged_delete = None
        self.message.hide()

        try:
            os.remove(staged_path)
        except OSError as error:
            # Left where it is, the file can still be recovered by hand
            logger.error(f"Could not remove deleted note {staged_path}: {error}")

    def export_note(self, file_path):
        """Copy a note to a file of the user's choosing"""
        note = self.note_at(file_path)
        name = (notes_model.label(note) if note else "") or Path(file_path).stem

        # Ask for export location
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Note",
            os.path.expanduser(f"~/Documents/{name}.md"),
            "Markdown Files (*.md);;All Files (*)",
        )

        if not export_path:
            return

        # Copy the file
        try:
            shutil.copy2(file_path, export_path)
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

            # If it's a note for the current card, just open it
            self.open_note_path(str(note_info.path))

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
