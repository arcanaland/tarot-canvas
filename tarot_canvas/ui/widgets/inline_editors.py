"""Editors that display text they edit until hovered or focused"""

from PyQt6.QtCore import QMargins, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QStyle,
    QStyleOptionFrame,
)

LINE_EDIT_TEXT_MARGIN = 2


class _Saved:
    """The saved text, and the frame shown only on hover or focus"""

    def _init_saved(self, framed_inset):
        self._saved = ""
        self._hovered = False
        self._framed_inset = framed_inset
        self._inset = framed_inset

    def natural_inset(self):
        """How far in from the left edge the text sits with the frame shown"""
        return self._framed_inset

    def set_text_inset(self, inset):
        """Hold the text inset px in, framed or not; no less than natural_inset()"""
        self._inset = max(inset, self._framed_inset)
        self._frame()

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
        self._framed_margins = self._contents_margins(framed=True)
        self._unframed_margins = self._contents_margins(framed=False)
        self._init_saved(self._framed_margins.left() + LINE_EDIT_TEXT_MARGIN)
        self.editingFinished.connect(self._commit)
        self._frame()

    def _text(self):
        return self.text()

    def _show(self, text):
        self.setText(text)
        self.setCursorPosition(0)

    def _contents_margins(self, framed):
        """The style's inset of the text area, with or without the frame"""
        option = QStyleOptionFrame()
        self.initStyleOption(option)
        option.lineWidth = (
            self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, option, self)
            if framed
            else 0
        )
        # Room enough that no style drops the frame for want of it
        option.rect = QRect(0, 0, 1000, 1000)
        inner = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, self)
        outer = option.rect
        return QMargins(
            inner.left() - outer.left(),
            inner.top() - outer.top(),
            outer.right() - inner.right(),
            outer.bottom() - inner.bottom(),
        )

    def _set_framed(self, framed):
        self.setFrame(framed)
        full = self._framed_margins
        shown = full if framed else self._unframed_margins
        # Unframed, the text margins stand in for the frame, keeping text and height still
        side = self._inset - LINE_EDIT_TEXT_MARGIN - shown.left()
        self.setTextMargins(side, full.top() - shown.top(), side, full.bottom() - shown.bottom())

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
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._frame_width = self.frameWidth()
        self._init_saved(self._frame_width + self._document_margin())
        self._lines = (min_lines, max_lines)
        self.setTabChangesFocus(True)
        self.document().contentsChanged.connect(self._fit)
        self._frame()

    def _text(self):
        return self.toPlainText()

    def _show(self, text):
        self.setPlainText(text)

    def _document_margin(self):
        return round(self.document().documentMargin())

    def _set_framed(self, framed):
        self.setFrameShape(QFrame.Shape.StyledPanel if framed else QFrame.Shape.NoFrame)
        # Unframed, viewport margins stand in for the frame, keeping text and height still
        shown = self._frame_width if framed else 0
        side = self._inset - shown - self._document_margin()
        edge = self._frame_width - shown
        self.setViewportMargins(side, edge, side, edge)
        self._fit()

    def _fit(self):
        least, most = self._lines
        # A plain-text layout's height is in lines
        lines = round(self.document().documentLayout().documentSize().height())
        lines = min(most, max(least, lines))
        # Room for the frame whether it's shown or not, so hovering doesn't change the height
        height = (
            lines * self.fontMetrics().lineSpacing()
            + 2 * self._document_margin()
            + 2 * self._frame_width
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
