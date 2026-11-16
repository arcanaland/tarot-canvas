import logging
import os
import shutil
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models import staged_delete
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui import commands, typography, units
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.commands import Scope
from tarot_canvas.ui.library.notes.model import NoteRole, NotesListModel
from tarot_canvas.ui.library.row_delegate import NoteRowDelegate
from tarot_canvas.ui.strings import NOTES, notes_text
from tarot_canvas.ui.tabs.card_view.markdown_editor import MarkdownEditor
from tarot_canvas.ui.tabs.card_view.note_editing import NoteLinks, write_note
from tarot_canvas.ui.tabs.card_view.notes_list import NotesEmptyPage, NotesListPage
from tarot_canvas.ui.widgets.heading_edit import heading_edit
from tarot_canvas.ui.widgets.inline_message import InlineMessage

log = logging.getLogger(__name__)


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
    """The notes kept in one directory: a card's, or anything else's with notes of its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        # Where the listed notes live and new ones are written; see set_anchor
        self.anchor = None
        self.anchor_notes = []  # [Note] in the anchor's directory, newest first
        self.links = NoteLinks(
            parent, getattr(parent, "deck_library", None), self.card_id, self.open_note_path
        )
        self.current_file_path = None

        # A note the user asked for but hasn't written yet
        self.pending_path = None
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
        self.open_action = QAction(QIcon.fromTheme("document-open"), notes_text("open"), self)
        self.open_action.triggered.connect(self.open_target)

        actions = commands.bind(
            self,
            Scope.NOTES,
            {"notes.rename": self.rename_target, "notes.delete": self.delete_target},
            # On the list and in the menus only, so the editor keeps F2 and Delete
            detached={"notes.rename", "notes.delete"},
        )
        self.rename_action = actions["notes.rename"]

        self.export_action = QAction(QIcon.fromTheme("document-export"), notes_text("export"), self)
        self.export_action.triggered.connect(self.export_target)

        self.delete_action = actions["notes.delete"]

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

        self.new_note_action = QAction(
            QIcon.fromTheme("document-new"), notes_text("create_note"), self
        )
        self.new_note_action.setToolTip(notes_text("new_note_tooltip"))
        self.new_note_action.triggered.connect(self.create_new_note)

        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), notes_text("undo"), self)
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
        self.message = InlineMessage(close_text=notes_text("dismiss"))
        self.message.dismissed.connect(self.commit_pending_delete)
        message_row.addWidget(self.message)
        layout.addLayout(message_row)

        # Create stacked widget to switch between notes list and editor
        self.stack = QStackedWidget()

        self.empty_page = NotesEmptyPage(self.new_note_action)

        self.list_model = NotesListModel(
            parent=self, card_in_subtitle=False, editable=True, stub_preview=notes_text("stub_note")
        )
        # Queued: the rename rescans and resets the model the editor is committing to
        self.list_model.renameRequested.connect(
            self.rename_note_to, Qt.ConnectionType.QueuedConnection
        )
        self.row_delegate = NoteRowDelegate(
            self,
            thumbnail=False,
            menu_button=True,
            menu_tooltip=notes_text("note_menu_tooltip"),
            reading=True,
        )
        self.row_delegate.menuRequested.connect(
            lambda index, pos: self.show_note_menu(self.path_at(index), pos)
        )

        self.list_page = NotesListPage(self.list_model, self.row_delegate, self.new_note_action)
        self.list_view = typography.apply(self.list_page.view, typography.Role.BODY, reading=True)
        self.list_view.activated.connect(lambda index: self.open_note_editor(self.path_at(index)))
        activate_on_return(self.list_view)
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
        back_button.setToolTip(NOTES["back_tooltip"])
        back_button.setMaximumSize(32, 32)
        back_button.clicked.connect(self.show_note_list)
        header_layout.addWidget(back_button)

        # The note's name (editable)
        self.note_title = heading_edit(notes_text("name_placeholder"))
        self.note_title.editingFinished.connect(self.apply_title_edit)
        header_layout.addWidget(self.note_title)

        # Save button
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon.fromTheme("document-save"))
        self.save_button.setToolTip(NOTES["save_tooltip"])
        self.save_button.setMaximumSize(32, 32)
        self.save_button.clicked.connect(self.save_current_note)
        header_layout.addWidget(self.save_button)

        self.editor_menu_button = QToolButton()
        self.editor_menu_button.setIcon(QIcon.fromTheme("overflow-menu"))
        self.editor_menu_button.setToolTip(notes_text("note_menu_tooltip"))
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
        self.note_editor.linkClicked.connect(self.links.follow)
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
        card_id = card.canonical_id if card else None
        self.set_anchor(notes_model.card_anchor(card_id) if card_id else None)

    def set_anchor(self, anchor):
        """List the notes under `anchor` and write new ones there; None lists nothing new."""
        self.discard_pending_note()

        # Moving to another anchor hides the Undo, so the delete it offered is final
        self.commit_pending_delete()

        # Moving to another anchor mustn't leave an edit waiting on the autosave timer
        self.save_if_modified()

        self.anchor = anchor

        if anchor is None:
            return

        # Ensure deck manager reference is passed to editor
        if hasattr(self.parent_tab, "deck_library"):
            self.note_editor.set_deck_library(self.parent_tab.deck_library)
            log.debug("Passed deck manager to editor")

        # The directory is made when the first note is written, not when a card is opened
        self.current_file_path = None
        self.refresh_list()
        self.show_list_or_empty_page()

    # -- the list -----------------------------------------------------------

    def refresh_list(self):
        """Re-read the index and show the anchor's notes, keeping the open note selected."""
        self.load_all_notes()

        key = self.anchor.directory.name if self.anchor else None
        self.list_model.set_card_notes(key, self.anchor_notes)
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
        return next((note for note in self.anchor_notes if str(note.path) == file_path), None)

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
            QMessageBox.critical(self, NOTES["error"], NOTES["load_failed"].format(error=e))

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
            QMessageBox.critical(self, NOTES["error"], NOTES["rename_failed"].format(error=error))
            return None

        if self.current_file_path == file_path:
            self.current_file_path = new_file_path

        self.refresh_list()
        note_events().notes_changed.emit()
        return new_file_path

    def card_id(self):
        """The card the anchor is about, if any."""
        return self.anchor.card_id if self.anchor else None

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
        if self.anchor is None:
            return

        # save whatever is open
        self.save_if_modified()

        self.current_file_path = None
        self.pending_name = ""
        self.pending_path = str(self.anchor.directory / f"{int(time.time())}.md")

        self.note_title.setText("")
        self.note_editor.clear()
        self.note_editor.setEnabled(True)
        self.note_editor.document().setModified(False)

        self.stack.setCurrentWidget(self.editor_page)
        self.note_editor.setFocus()

    def discard_pending_note(self):
        """Forget a note that was asked for but never written."""
        self.pending_path = None

    def write_pending_note(self):
        """Give a pending note a file."""
        if not self.pending_path or not self.note_editor.toPlainText().strip():
            return

        file_path = renamed_path(self.pending_path, self.pending_name)

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        except OSError as error:
            error_msg = NOTES["mkdir_failed"].format(error=error)
            log.exception(error_msg)
            QMessageBox.critical(self, NOTES["error"], error_msg)
            return

        self.pending_path = None
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

        try:
            staged_path = staged_delete.stage(file_path)
        except OSError as error:
            QMessageBox.critical(self, NOTES["error"], NOTES["delete_failed"].format(error=error))
            return

        self.staged_delete = (file_path, staged_path)
        self.show_note_list()
        note_events().notes_changed.emit()
        self.message.show_message(notes_text("deleted_message"), [self.undo_action])

    def undo_delete(self):
        if not self.staged_delete:
            return

        file_path, staged_path = self.staged_delete
        self.staged_delete = None
        self.message.hide()

        try:
            staged_delete.restore(staged_path, file_path)
        except OSError as error:
            QMessageBox.critical(self, NOTES["error"], NOTES["restore_failed"].format(error=error))
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
            staged_delete.commit(staged_path)
        except OSError as error:
            # Left where it is, the file can still be recovered by hand
            log.exception("Could not remove deleted note %s: %s", staged_path, error)

    def export_note(self, file_path):
        """Copy a note to a file of the user's choosing"""
        note = self.note_at(file_path)
        name = (notes_model.label(note) if note else "") or Path(file_path).stem

        # Ask for export location
        export_path, _ = QFileDialog.getSaveFileName(
            self,
            NOTES["export"],
            os.path.expanduser(f"~/Documents/{name}.md"),
            NOTES["export_filter"],
        )

        if not export_path:
            return

        # Copy the file
        try:
            shutil.copy2(file_path, export_path)
        except Exception as e:
            QMessageBox.critical(self, NOTES["error"], NOTES["export_failed"].format(error=e))

    # Helper methods

    def load_all_notes(self):
        """Re-read the anchor's notes, and every card's for linking"""
        self.anchor_notes = notes_model.read_directory(self.anchor.directory) if self.anchor else []
        self.links.refresh()

    @property
    def notes_index(self):
        """card_id -> [Note], the whole card library"""
        return self.links.notes_index

    def get_link_suggestions(self):
        """What the editor's link completer offers"""
        return self.links.suggestions()

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
        try:
            write_note(file_path, self.note_editor.toPlainText())
            self.load_all_notes()
            note_events().notes_changed.emit()

        except Exception as e:
            error_msg = NOTES["save_failed"].format(error=e)
            log.exception(error_msg)
            QMessageBox.critical(self, NOTES["error"], error_msg)

    def find_note_by_title(self, note_name):
        return self.links.find_note_by_title(note_name)

    def auto_save(self):
        """Automatically save the current note if modified"""
        path = self.current_file_path
        if self.save_if_modified():
            log.debug("Auto-saved note: %s", path)
