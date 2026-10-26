"""Every card of a deck in a wrapping grid"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QListView

from tarot_canvas.ui.library import units

Cursor = QAbstractItemView.CursorAction


class SectionsView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(False)
        self.setSpacing(units.LARGE_SPACING)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)

    # -- height -------------------------------------------------------------

    def contents_height(self):
        """The laid-out items' height, with the spacing below the last line"""
        model = self.model()
        if model is None or not model.rowCount():
            return 0
        bottom = max(
            self.rectForIndex(model.index(row, 0)).bottom() for row in range(model.rowCount())
        )
        return bottom + 1 + self.spacing()

    def updateGeometries(self):
        super().updateGeometries()
        # PyQt doesn't expose contentsSize()
        height = self.contents_height() + 2 * self.frameWidth()
        if height != self.height():
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        if event.size().width() != event.oldSize().width() and self.model() is not None:
            self.itemDelegate().lines_resized(self.model())
        super().resizeEvent(event)

    def wheelEvent(self, event):
        # Nothing here scrolls
        event.ignore()

    # -- the keyboard -------------------------------------------------------

    def _card_rows(self):
        return [
            row
            for row in range(self.model().rowCount())
            if self.model().flags(self.model().index(row, 0)) & Qt.ItemFlag.ItemIsSelectable
        ]

    def moveCursor(self, action, modifiers):
        """Left and Right step through the deck in order, across headings; Up and Down
        go to the nearest card on the next line"""
        model = self.model()
        rows = self._card_rows() if model is not None else []
        if not rows:
            return super().moveCursor(action, modifiers)
        current = self.currentIndex()
        if not current.isValid() or current.row() not in rows:
            return model.index(rows[0], 0)

        if self.isRightToLeft():
            swapped = {Cursor.MoveLeft: Cursor.MoveRight, Cursor.MoveRight: Cursor.MoveLeft}
            action = swapped.get(action, action)
        position = rows.index(current.row())
        if action in (Cursor.MoveRight, Cursor.MoveNext):
            return model.index(rows[min(position + 1, len(rows) - 1)], 0)
        if action in (Cursor.MoveLeft, Cursor.MovePrevious):
            return model.index(rows[max(position - 1, 0)], 0)
        if action == Cursor.MoveHome:
            return model.index(rows[0], 0)
        if action == Cursor.MoveEnd:
            return model.index(rows[-1], 0)
        if action in (Cursor.MoveDown, Cursor.MoveUp):
            return self._card_on_next_line(current, rows, action == Cursor.MoveDown)

        target = super().moveCursor(action, modifiers)
        if target.isValid() and target.row() in rows:
            return target
        return current

    def _card_on_next_line(self, current, rows, down):
        here = self.rectForIndex(current)
        lines = {}
        for row in rows:
            rect = self.rectForIndex(self.model().index(row, 0))
            if (rect.top() > here.top()) if down else (rect.top() < here.top()):
                lines.setdefault(rect.top(), []).append((row, rect))
        if not lines:
            return current
        line = lines[min(lines) if down else max(lines)]
        row, _ = min(line, key=lambda item: abs(item[1].center().x() - here.center().x()))
        return self.model().index(row, 0)
