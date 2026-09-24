from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeySequence, QShortcut


class _EmptyClickFilter(QObject):
    def __init__(self, view):
        super().__init__(view)
        self._view = view

    def eventFilter(self, _watched, event):
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and not self._view.indexAt(event.position().toPoint()).isValid()
        ):
            clear_selection(self._view)
        return False


def clear_selection(view):
    view.selectionModel().clear()


def deselect_on_empty_click_or_escape(view):
    view.viewport().installEventFilter(_EmptyClickFilter(view))
    escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), view)
    escape.setContext(Qt.ShortcutContext.WidgetShortcut)
    escape.activated.connect(lambda: clear_selection(view))
