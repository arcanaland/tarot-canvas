"""The Edit menu's commands on a focused text field"""

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QPlainTextEdit, QTextEdit


def field():
    """The focused widget, if the Edit menu should act on its text"""
    widget = QApplication.focusWidget()
    if isinstance(widget, QLineEdit | QTextEdit | QPlainTextEdit):
        return widget
    if isinstance(widget, QLabel) and widget.hasSelectedText():
        return widget
    return None


def _has_selection(widget):
    if isinstance(widget, QLineEdit | QLabel):
        return widget.hasSelectedText()
    return widget.textCursor().hasSelection()


def _editable(widget):
    return not isinstance(widget, QLabel) and not widget.isReadOnly()


def can(how, widget):
    """Whether the field takes how: cut, copy, paste, delete, select_all, deselect"""
    if widget is None:
        return False
    if how == "copy":
        return _has_selection(widget)
    if isinstance(widget, QLabel):
        return False
    if how == "cut":
        return _editable(widget) and _has_selection(widget)
    if how in ("paste", "delete"):
        return _editable(widget)
    if how == "select_all":
        return True
    return how == "deselect" and _has_selection(widget)


def run(how, widget):
    if how == "copy" and isinstance(widget, QLabel):
        QGuiApplication.clipboard().setText(widget.selectedText())
    elif how == "delete" and isinstance(widget, QLineEdit):
        widget.del_()
    elif how == "delete":
        widget.textCursor().deleteChar()
    elif how == "deselect" and isinstance(widget, QLineEdit):
        widget.deselect()
    elif how == "deselect":
        cursor = widget.textCursor()
        cursor.clearSelection()
        widget.setTextCursor(cursor)
    else:
        actions = {"cut": widget.cut, "copy": widget.copy, "paste": widget.paste}
        actions.get(how, widget.selectAll)()
