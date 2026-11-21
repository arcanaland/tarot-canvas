"""A delete that waits under an inline Undo, one at a time, until it is made final."""

import logging

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models import staged_delete

log = logging.getLogger(__name__)


class PendingDelete(QObject):
    """The one delete an InlineMessage offers to undo

    The owner says how a path is moved aside (stage, returning where it went), brought back
    (restore) and removed for good (commit); by default these are staged_delete's. The delete
    becomes final on the next delete, when the message is dismissed, when the owner calls
    commit() or when the app quits.
    """

    delete_failed = pyqtSignal(object)  # the OSError
    restored = pyqtSignal(object)  # the path, back where it was
    restore_failed = pyqtSignal(object)  # the OSError
    committed = pyqtSignal(object)  # the path, now gone for good

    def __init__(
        self,
        message,
        undo_text,
        parent=None,
        *,
        stage=None,
        restore=None,
        commit=None,
    ):
        super().__init__(parent)
        self._message = message
        # Looked up when called, not bound here, so staged_delete can be patched in tests
        self._stage = stage or (lambda path: staged_delete.stage(path))
        self._restore = restore or (lambda staged, path: staged_delete.restore(staged, path))
        self._commit = commit or (lambda staged: staged_delete.commit(staged))

        # (path, where it was staged) of the delete that can still be undone
        self.staged = None

        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), undo_text, self)
        self.undo_action.triggered.connect(self.undo)
        message.dismissed.connect(self.commit)

        # Closing the window closes no tab, so quitting is the last chance to commit
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.commit)

    def delete(self, path, text):
        """Stage path and offer its Undo under text; whether it was staged"""
        # One Undo at a time: the delete it offered becomes final
        self.commit()
        try:
            staged = self._stage(path)
        except OSError as error:
            log.error("Could not delete %s: %s", path, error)
            self.delete_failed.emit(error)
            return False
        self.staged = (path, staged)
        self._message.show_message(text, [self.undo_action])
        return True

    @pyqtSlot()
    def undo(self):
        if self.staged is None:
            return
        path, staged = self.staged
        self.staged = None
        self._message.hide()
        try:
            self._restore(staged, path)
        except OSError as error:
            log.error("Could not restore %s: %s", path, error)
            self.restore_failed.emit(error)
            return
        self.restored.emit(path)

    @pyqtSlot()
    def commit(self):
        """Make the staged delete final"""
        if self.staged is None:
            return
        path, staged = self.staged
        self.staged = None
        self._message.hide()
        try:
            self._commit(staged)
        except OSError as error:
            # Left where it is, it can still be recovered by hand
            log.error("Could not remove deleted %s: %s", staged, error)
            return
        self.committed.emit(path)
