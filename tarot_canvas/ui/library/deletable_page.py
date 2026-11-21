from pathlib import Path

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QVBoxLayout

from tarot_canvas.ui import units
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.strings import notes_text
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.ui.widgets.pending_delete import PendingDelete


class DeletableListPage(LibraryListPage):
    """A list page whose rows are folders, deleted under an inline Undo

    The folder is moved aside until the next delete, the message's dismissal or quitting.
    """

    folders_changed = pyqtSignal()  # a folder was moved aside or put back

    def __init__(self, list_model, delegate_class, details_pane, parent, *, texts):
        super().__init__(list_model, delegate_class, details_pane, parent)
        # The deleted, delete_failed and restore_failed messages
        self._texts = texts

        # Hidden, it takes no room, margins included
        message_row = QVBoxLayout()
        margin = units.LARGE_SPACING
        message_row.setContentsMargins(margin, margin, margin, 0)
        self.message = InlineMessage(close_text=notes_text("dismiss"))
        message_row.addWidget(self.message)
        self.layout().insertLayout(0, message_row)

        self.pending = PendingDelete(self.message, notes_text("undo"), self)
        self.pending.delete_failed.connect(lambda _error: self._show_text("delete_failed"))
        self.pending.restore_failed.connect(lambda _error: self._show_text("restore_failed"))
        self.pending.restored.connect(self._on_restored)
        self.pending.committed.connect(self._forget)

    @property
    def staged(self):
        """(folder, staged path) of a delete that can still be undone"""
        return self.pending.staged

    @property
    def undo_action(self):
        return self.pending.undo_action

    def select(self, path):
        raise NotImplementedError

    def _forget(self, path):
        """Whatever is kept about the folder elsewhere goes once its delete is final"""

    def _show_text(self, key):
        self.message.show_message(self._texts[key])

    def delete(self, path, text=None):
        """Take the folder out of every view now; remove it once Undo is gone. Whether it was"""
        staged = self.pending.delete(Path(path), text or self._texts["deleted"])
        if staged:
            self.folders_changed.emit()
        return staged

    @pyqtSlot()
    def undo_delete(self):
        self.pending.undo()

    def _on_restored(self, path):
        self.folders_changed.emit()
        self.select(path)

    @pyqtSlot()
    def commit_pending_delete(self):
        """Make the staged delete final"""
        self.pending.commit()
