"""Every card of a deck in one wrapping grid, each section under a heading of its own"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QListView

from tarot_canvas.ui.deck_view.card_model import KIND_HEADING, KindRole
from tarot_canvas.ui.library import units

Cursor = QAbstractItemView.CursorAction


class SectionsView(QListView):
    """A grid that is as tall as its contents, for a page that does the scrolling.

    Headings and notes are rows as wide as the view, so each takes a line; the
    delegate is asked for their size again whenever the width changes.
    """

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
        # The page's ground shows through, not a well of Base inside it
        self.viewport().setAutoFillBackground(False)
        self._heading_widget = None

    # -- the first heading's line -------------------------------------------

    def set_heading_widget(self, widget):
        """Put widget at the right end of the first heading's line, which grows to hold it.
        Call it once the delegate is set."""
        self._heading_widget = widget
        widget.setParent(self.viewport())
        self.itemDelegate().set_heading_line_min(widget.sizeHint().height())
        self.scheduleDelayedItemsLayout()

    def _first_heading(self):
        model = self.model()
        for row in range(model.rowCount() if model is not None else 0):
            index = model.index(row, 0)
            if index.data(KindRole) == KIND_HEADING:
                return index
        return None

    def _place_heading_widget(self):
        widget = self._heading_widget
        if widget is None:
            return
        heading = self._first_heading()
        if heading is None:
            widget.hide()
            return
        line, _ = self.itemDelegate().heading_layout(self.visualRect(heading), heading.row())
        size = widget.sizeHint()
        widget.setGeometry(
            line.right() + 1 - size.width(),
            line.top() + (line.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )
        widget.show()

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
        self._place_heading_widget()

    def resizeEvent(self, event):
        if event.size().width() != event.oldSize().width() and self.model() is not None:
            self.itemDelegate().lines_resized(self.model())
        super().resizeEvent(event)

    def wheelEvent(self, event):
        # Nothing here scrolls, so the page under it does
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
        go to the nearest card on the next line, never to a heading"""
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
