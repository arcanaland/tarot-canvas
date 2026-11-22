"""The decks' covers on their shelves"""

from PyQt6.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView

from tarot_canvas.ui.library.section_row import is_section
from tarot_canvas.ui.widgets.heading_grid import HeadingGrid


class DeckGrid(HeadingGrid):
    """Clicking a heading leaves the selection and the current cover alone"""

    heading_clicked = pyqtSignal()  # one that folds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._heading_pressed = False
        self._folds = False

    def is_stop(self, index):
        return bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)

    def selectionCommand(self, index, event=None):
        if is_section(index):
            return QItemSelectionModel.SelectionFlag.NoUpdate
        return super().selectionCommand(index, event)

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        """A cover on its shelf's first line brings the heading along"""
        super().scrollTo(index, hint)
        cover = self.visualRect(index)
        for row in reversed(range(index.row())):
            above = self.model().index(row, 0)
            rect = self.visualRect(above)
            if is_section(above):
                top = rect.top() - self.spacing()
                if top < 0 and cover.bottom() - top < self.viewport().height():
                    bar = self.verticalScrollBar()
                    bar.setValue(bar.value() + top)
                return
            if rect.top() < cover.top():
                return

    def mousePressEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        self._heading_pressed = is_section(index)
        self._folds = (
            self._heading_pressed
            and event.button() == Qt.MouseButton.LeftButton
            and self.is_stop(index)
        )
        if not self._heading_pressed:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._heading_pressed = is_section(self.indexAt(event.position().toPoint()))
        self._folds = False
        if not self._heading_pressed:
            super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._heading_pressed:
            super().mouseReleaseEvent(event)
            return
        folds, self._folds = self._folds, False
        self._heading_pressed = False
        index = self.indexAt(event.position().toPoint())
        if folds and is_section(index) and self.is_stop(index):
            self.heading_clicked.emit()
