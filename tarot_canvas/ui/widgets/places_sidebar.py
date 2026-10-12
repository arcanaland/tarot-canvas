from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QListView, QListWidget, QListWidgetItem

from tarot_canvas.ui.library import units


class PlacesSidebar(QListWidget):
    """A frameless column of places down a window's edge (inspired by Dolphin's Places panel)"""

    def __init__(self, rows, parent=None, *, filled=False):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        if filled:
            self.setBackgroundRole(QPalette.ColorRole.Base)
            self.setAutoFillBackground(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(units.SMALL_SPACING // 2)

        for icon, name, data in rows:
            item = QListWidgetItem(icon, name)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.addItem(item)

        # A click on no row, or a Ctrl+click on the current one, must not leave none chosen
        self.itemSelectionChanged.connect(self._keep_a_row_selected)

        self.setFixedWidth(self.sizeHintForColumn(0) + 2 * units.LARGE_SPACING + units.GRID_UNIT)

    def center_first_row_on(self, header_height):
        """Line the first row up with a header `header_height` tall beside the sidebar's top"""
        top = header_height // 2 - self.sizeHintForRow(0) // 2 - self.spacing()
        self.setViewportMargins(0, max(0, top), 0, 0)

    def _keep_a_row_selected(self):
        if not self.selectedItems() and self.currentItem() is not None:
            self.currentItem().setSelected(True)
