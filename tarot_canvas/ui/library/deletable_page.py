from pathlib import Path

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QVBoxLayout

from tarot_canvas.models import staged_delete
from tarot_canvas.ui import units
from tarot_canvas.ui.library.list_page import LibraryListPage
from tarot_canvas.ui.strings import notes_text
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.utils.logger import logger


class DeletableListPage(LibraryListPage):
    """A list page whose rows are folders, deleted under an inline Undo

    The folder is moved aside until the next delete, the message's dismissal or quitting.
    """

    def __init__(self, list_model, delegate_class, details_pane, parent, *, changed, texts):
        super().__init__(list_model, delegate_class, details_pane, parent)
        # The signal that makes every view rescan, and the deleted, delete_failed and
        # restore_failed messages
        self._changed = changed
        self._texts = texts

        # (folder, staged path) of a delete that can still be undone
        self.staged = None

        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), notes_text("undo"), self)
        self.undo_action.triggered.connect(self.undo_delete)

        # Hidden, it takes no room, margins included
        message_row = QVBoxLayout()
        margin = units.LARGE_SPACING
        message_row.setContentsMargins(margin, margin, margin, 0)
        self.message = InlineMessage(close_text=notes_text("dismiss"))
        self.message.dismissed.connect(self.commit_pending_delete)
        message_row.addWidget(self.message)
        self.layout().insertLayout(0, message_row)

        # Closing the window closes no tab, so quitting is the last chance to commit
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.commit_pending_delete)

    def select(self, path):
        raise NotImplementedError

    def delete(self, path):
        """Take the folder out of every view now; remove it once Undo is gone"""
        # One Undo at a time: the delete it offered becomes final
        self.commit_pending_delete()

        try:
            staged = staged_delete.stage(path)
        except OSError as error:
            logger.error(f"Could not delete {path}: {error}")
            self.message.show_message(self._texts["delete_failed"])
            return

        self.staged = (Path(path), staged)
        self._changed.emit()
        self.message.show_message(self._texts["deleted"], [self.undo_action])

    @pyqtSlot()
    def undo_delete(self):
        if self.staged is None:
            return

        path, staged = self.staged
        self.staged = None
        self.message.hide()

        try:
            staged_delete.restore(staged, path)
        except OSError as error:
            logger.error(f"Could not restore {path}: {error}")
            self.message.show_message(self._texts["restore_failed"])
            return

        self._changed.emit()
        self.select(path)

    @pyqtSlot()
    def commit_pending_delete(self):
        """Make the staged delete final"""
        if self.staged is None:
            return

        _path, staged = self.staged
        self.staged = None
        self.message.hide()

        try:
            staged_delete.commit(staged)
        except OSError as error:
            # Left where it is, the folder can still be recovered by hand
            logger.error(f"Could not remove deleted {staged}: {error}")
