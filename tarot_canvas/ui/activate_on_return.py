import sys

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractItemView

RETURN_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


class _ReturnFilter(QObject):
    def __init__(self, view):
        super().__init__(view)
        self._view = view

    def eventFilter(self, _watched, event):
        if event.type() != QEvent.Type.KeyPress or event.key() not in RETURN_KEYS:
            return False
        view = self._view
        index = view.currentIndex()
        if view.state() == QAbstractItemView.State.EditingState or not index.isValid():
            return False
        view.activated.emit(index)
        return True


def activate_on_return(view, platform=sys.platform):
    """Return emits `activated` on macOS too.

    Qt's item views emit it on Return everywhere but macOS, where Return
    is left to editing and ⌘O activates instead.
    """
    if platform == "darwin":
        view.installEventFilter(_ReturnFilter(view))
