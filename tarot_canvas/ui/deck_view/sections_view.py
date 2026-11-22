"""Every card of a deck in a wrapping grid"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QListView

from tarot_canvas.ui import units
from tarot_canvas.ui.widgets.heading_grid import HeadingGrid


class SectionsView(HeadingGrid):
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

    def wheelEvent(self, event):
        # Nothing here scrolls
        event.ignore()
