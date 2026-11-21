"""Editors that read as the text they edit until hovered or focused

Each keeps the text last saved: committed(text) fires when it loses focus (or on Return, for a
line) with text that differs from it, and Esc puts it back.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLineEdit, QPlainTextEdit, QStyle


class _Saved:
    """The saved text, and the frame shown only on hover or focus"""

    def _init_saved(self):
        self._saved = ""
        self._hovered = False

    def saved(self):
        return self._saved

    def set_saved(self, text):
        """text is what's on disk; shown unless the editor is being typed in"""
        self._saved = text
        if not self.hasFocus():
            self._show(text)

    def revert(self):
        self._show(self._saved)

    def _commit(self):
        if self._text() != self._saved:
            self.committed.emit(self._text())

    def _escape(self, event):
        """True when Esc put the saved text back"""
        if event.key() == Qt.Key.Key_Escape and self._text() != self._saved:
            self.revert()
            event.accept()
            return True
        return False

    def _hover(self, hovered):
        self._hovered = hovered
        self._frame()

    def _frame(self):
        framed = self._hovered or self.hasFocus()
        self._set_framed(framed)
        # Unframed, it shows the ground it sits on, as a label would
        palette = QPalette(self.palette())
        base = QApplication.palette(self).color(QPalette.ColorRole.Base)
        palette.setColor(
            QPalette.ColorRole.Base, base if framed else QColor(Qt.GlobalColor.transparent)
        )
        self.setPalette(palette)


class InlineLineEdit(_Saved, QLineEdit):
    committed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_saved()
        self.editingFinished.connect(self._commit)
        self._frame()

    def _text(self):
        return self.text()

    def _show(self, text):
        self.setText(text)
        self.setCursorPosition(0)

    def _set_framed(self, framed):
        self.setFrame(framed)

    def keyPressEvent(self, event):
        if not self._escape(event):
            super().keyPressEvent(event)

    def enterEvent(self, event):
        self._hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(False)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._frame()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._frame()


class InlineTextEdit(_Saved, QPlainTextEdit):
    """Return is a newline; it grows from min_lines to max_lines, then scrolls"""

    committed = pyqtSignal(str)

    def __init__(self, min_lines=2, max_lines=6, parent=None):
        super().__init__(parent)
        self._init_saved()
        self._lines = (min_lines, max_lines)
        self.setTabChangesFocus(True)
        self.document().contentsChanged.connect(self._fit)
        self._frame()

    def _text(self):
        return self.toPlainText()

    def _show(self, text):
        self.setPlainText(text)

    def _set_framed(self, framed):
        self.setFrameShape(QFrame.Shape.StyledPanel if framed else QFrame.Shape.NoFrame)
        self._fit()

    def _fit(self):
        least, most = self._lines
        # A plain-text layout's height is in lines
        lines = round(self.document().documentLayout().documentSize().height())
        lines = min(most, max(least, lines))
        # Room for the frame whether it's shown or not, so hovering doesn't change the height
        frame = self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, None, self)
        height = (
            lines * self.fontMetrics().lineSpacing()
            + 2 * round(self.document().documentMargin())
            + 2 * max(frame, self.frameWidth())
        )
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def keyPressEvent(self, event):
        if not self._escape(event):
            super().keyPressEvent(event)

    def enterEvent(self, event):
        self._hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(False)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._frame()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._frame()
        self._commit()
