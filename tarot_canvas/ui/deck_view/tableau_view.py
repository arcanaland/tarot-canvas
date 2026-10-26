"""A deck laid out by its structure, sized to show all of it"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QStyleOptionViewItem, QTableView

from tarot_canvas.ui.deck_view.tableau_model import ROW_GAP
from tarot_canvas.ui.library import units

Cursor = QAbstractItemView.CursorAction


class TableauView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setMouseTracking(True)
        self.setDragEnabled(False)
        self.setTabKeyNavigation(False)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)

    def setModel(self, model):
        old = self.model()
        if old is not None:
            old.modelReset.disconnect(self.update_sections)
        super().setModel(model)
        if model is not None:
            model.modelReset.connect(self.update_sections)
        self.update_sections()

    # -- size ---------------------------------------------------------------

    def _cell_size(self, row, column):
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        return self.itemDelegate().sizeHint(option, self.model().index(row, column))

    def update_sections(self):
        """Columns a card wide, rows as tall as what they hold; then the view takes
        its full size and the page scrolls instead"""
        model = self.model()
        if model is None or not model.card_cells():
            self.setFixedSize(QSize(0, 0))
            return

        width = self._cell_size(*model.card_cells()[0]).width()
        for column in range(model.columnCount()):
            self.horizontalHeader().resizeSection(column, width)
        for row in range(model.rowCount()):
            if model.row_kind(row) == ROW_GAP:
                height = units.GRID_UNIT
            else:
                height = max(
                    self._cell_size(row, column).height() for column in range(model.columnCount())
                )
            self.verticalHeader().resizeSection(row, height)

        self.setFixedSize(
            self.horizontalHeader().length() + 2 * self.frameWidth(),
            self.verticalHeader().length() + 2 * self.frameWidth(),
        )

    def wheelEvent(self, event):
        # Nothing here scrolls
        event.ignore()

    # -- the keyboard -------------------------------------------------------

    def moveCursor(self, action, modifiers):
        """Arrows step to the next card that way, over labels, ghosts and gaps"""
        model = self.model()
        cells = model.card_cells() if model is not None else []
        if not cells:
            return super().moveCursor(action, modifiers)
        current = self.currentIndex()
        here = (current.row(), current.column())
        if not current.isValid() or here not in cells:
            return model.index(*cells[0])

        if self.isRightToLeft():
            swapped = {Cursor.MoveLeft: Cursor.MoveRight, Cursor.MoveRight: Cursor.MoveLeft}
            action = swapped.get(action, action)
        row, column = here
        target = here
        if action == Cursor.MoveHome:
            target = cells[0]
        elif action == Cursor.MoveEnd:
            target = cells[-1]
        elif action in (Cursor.MoveLeft, Cursor.MoveRight):
            step = 1 if action == Cursor.MoveRight else -1
            along = [c for r, c in cells if r == row and (c - column) * step > 0]
            if along:
                target = (row, min(along, key=lambda c: abs(c - column)))
        elif action in (Cursor.MoveUp, Cursor.MoveDown):
            step = 1 if action == Cursor.MoveDown else -1
            rows = sorted({r for r, _ in cells if (r - row) * step > 0}, key=lambda r: abs(r - row))
            if rows:
                line = [c for r, c in cells if r == rows[0]]
                target = (rows[0], min(line, key=lambda c: (abs(c - column), c)))
        else:
            index = super().moveCursor(action, modifiers)
            if (index.row(), index.column()) in cells:
                return index
        return model.index(*target)
