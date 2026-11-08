"""The search field at the start of a page's header row"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLineEdit

# Plain keys that leave the field for its results; Ctrl+Return and the like stay commands
INTO_RESULTS_KEYS = (Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter)


def search_field(placeholder):
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    field.addAction(QIcon.fromTheme("search"), QLineEdit.ActionPosition.LeadingPosition)
    return field


class _IntoResults(QObject):
    def __init__(self, field, handler):
        super().__init__(field)
        self._handler = handler

    def eventFilter(self, _watched, event):
        if (
            event.type() != QEvent.Type.KeyPress
            or event.key() not in INTO_RESULTS_KEYS
            or event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        ):
            return False
        self._handler()
        return True


def step_into_results(field, handler):
    """↓ or Return in field calls handler(), which moves to the first result"""
    field.installEventFilter(_IntoResults(field, handler))
