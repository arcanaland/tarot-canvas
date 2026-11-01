from PyQt6.QtCore import QPersistentModelIndex, QPointF, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QAbstractItemView, QListView

from tarot_canvas.ui.palette import muted_text

GRIP_WIDTH = 16
GRIP_DOT = 3.0
GRIP_GAP = 3.0
GRIP_COLUMNS = 2
GRIP_ROWS = 3


def paint_grip(painter, rect, palette):
    """The dots that say a row can be picked up, centred in rect"""
    pitch = GRIP_DOT + GRIP_GAP
    left = rect.center().x() + 0.5 - (GRIP_COLUMNS * pitch - GRIP_GAP) / 2
    top = rect.center().y() + 0.5 - (GRIP_ROWS * pitch - GRIP_GAP) / 2

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(muted_text(palette))
    radius = GRIP_DOT / 2
    for column in range(GRIP_COLUMNS):
        for row in range(GRIP_ROWS):
            centre = QPointF(left + column * pitch + radius, top + row * pitch + radius)
            painter.drawEllipse(centre, radius, radius)
    painter.restore()


class ReorderListView(QListView):
    """A list whose rows move by drag and by Alt+Up and Alt+Down, through the model's moveRows.

    A row moves if it has ItemIsDragEnabled and the model's moveRows agrees. The model also
    needs ItemIsDropEnabled on the invalid index and a supportedDropActions of MoveAction
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

    def drop_row(self, point):
        """The row a drop at point lands before, numbered before the move"""
        index = self.indexAt(point)
        if not index.isValid():
            return self.model().rowCount(self.rootIndex())
        return index.row() + (point.y() > self.visualRect(index).center().y())

    def move_row(self, row, destination):
        """Move row to land before destination, numbered before the move"""
        index = self.model().index(row, 0, self.rootIndex())
        if not index.flags() & Qt.ItemFlag.ItemIsDragEnabled or destination in (row, row + 1):
            return False
        moved = QPersistentModelIndex(index)
        root = self.rootIndex()
        if not self.model().moveRow(root, row, root, destination):
            return False
        self.scrollTo(self.model().index(moved.row(), 0, root))
        return True

    def step_row(self, row, step):
        """Move row one place up (-1) or down (1), stopping at the ends"""
        if not 0 <= row + step < self.model().rowCount(self.rootIndex()):
            return False
        return self.move_row(row, row + 2 if step > 0 else row - 1)

    def dropEvent(self, event):
        current = self.currentIndex()
        if current.isValid():
            self.move_row(current.row(), self.drop_row(event.position().toPoint()))

        # A drop reported as a move has startDrag call removeRows on the dragged row. Only
        # Ignore gets past setDropAction: InternalMove's drag offers nothing but Move
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self.viewport().update()

    def keyPressEvent(self, event):
        step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(event.key())
        if step is None or event.modifiers() != Qt.KeyboardModifier.AltModifier:
            super().keyPressEvent(event)
            return
        current = self.currentIndex()
        if current.isValid():
            self.step_row(current.row(), step)
        event.accept()
