"""A wrapping grid with headings as wide as the view"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QListView

Cursor = QAbstractItemView.CursorAction


class HeadingGrid(QListView):
    def resizeEvent(self, event):
        if event.size().width() != event.oldSize().width() and self.model() is not None:
            # Headings and notes are as wide as the view, so their size hints just changed
            self.scheduleDelayedItemsLayout()
        super().resizeEvent(event)

    # -- the keyboard -------------------------------------------------------

    def is_stop(self, index):
        """Whether the cursor rests on index"""
        return bool(index.flags() & Qt.ItemFlag.ItemIsSelectable)

    def moveCursor(self, action, modifiers):
        """Left and Right step through the items in order, across headings; Up and Down
        go to the nearest on the next line"""
        model = self.model()
        rows = []
        if model is not None:
            rows = [row for row in range(model.rowCount()) if self.is_stop(model.index(row, 0))]
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
            return self._stop_on_next_line(current, rows, action == Cursor.MoveDown)

        target = super().moveCursor(action, modifiers)
        if not target.isValid():
            return current
        if target.row() in rows:
            return target
        # A page that ends on a heading goes on to the item past it
        if action == Cursor.MovePageDown:
            return model.index(next((r for r in rows if r > target.row()), rows[-1]), 0)
        if action == Cursor.MovePageUp:
            return model.index(next((r for r in reversed(rows) if r < target.row()), rows[0]), 0)
        return current

    def _stop_on_next_line(self, current, rows, down):
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
