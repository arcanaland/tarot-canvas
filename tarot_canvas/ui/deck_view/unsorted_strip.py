"""A created deck's images that are in no slot yet"""

import os
from pathlib import Path

from PyQt6.QtCore import QMimeData, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPalette, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QLabel, QMenu, QVBoxLayout, QWidget

from tarot_canvas.models.deck_writer import UNSORTED
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.strings import DECK_VIEW

PathRole = Qt.ItemDataRole.UserRole + 1


def local_files(mime):
    if not mime.hasUrls():
        return []
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


class _UnsortedModel(QStandardItemModel):
    """Items drag out as their file"""

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, indexes):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(index.data(PathRole)) for index in indexes])
        return mime

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction


class UnsortedView(SectionsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)


class UnsortedStrip(QWidget):
    # Local files dropped here
    files_dropped = pyqtSignal(list)
    discard_requested = pyqtSignal(str)  # a file name in unsorted/

    def __init__(self, deck_path, cover_size, parent=None):
        super().__init__(parent)
        self.folder = Path(deck_path) / UNSORTED
        self._cover_size = cover_size
        self._covers = CoverCache(capacity=128)
        self.setAcceptDrops(True)

        heading = QLabel(DECK_VIEW["unsorted"])
        typography.apply(heading, typography.Role.HEADING_2)

        self.empty_label = QLabel(DECK_VIEW["unsorted_empty"])
        self.empty_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.model = _UnsortedModel(self)
        self.view = UnsortedView()
        self.view.setModel(self.model)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addWidget(heading)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.view)
        self.reload()

    def names(self):
        return [self.model.item(row).text() for row in range(self.model.rowCount())]

    def current_name(self):
        index = self.view.currentIndex()
        return index.data() if index.isValid() else None

    def set_cover_size(self, cover_size):
        self._cover_size = cover_size
        self._covers.clear()
        self.reload()

    def reload(self):
        current = self.current_name()
        self.model.clear()
        try:
            entries = [
                entry
                for entry in os.scandir(self.folder)
                if entry.is_file() and not entry.name.startswith(".")
            ]
        except FileNotFoundError:
            entries = []
        size = QSize(self._cover_size)
        width, height = size.width(), size.height()
        self.view.setIconSize(size)
        line = QFontMetrics(self.view.font()).height()
        self.view.setGridSize(
            QSize(width + 2 * units.LARGE_SPACING, height + line + 2 * units.LARGE_SPACING)
        )
        dpr = self.devicePixelRatioF()
        for entry in sorted(entries, key=lambda entry: entry.name):
            item = QStandardItem(entry.name)
            item.setData(entry.path, PathRole)
            item.setToolTip(entry.name)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            pixmap = self._covers.get(entry.path, size, dpr)
            if pixmap is not None:
                item.setIcon(QIcon(pixmap))
            self.model.appendRow(item)
            if entry.name == current:
                self.view.setCurrentIndex(item.index())
        self.empty_label.setVisible(not entries)
        self.view.setVisible(bool(entries))

    def _on_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        self.view.setCurrentIndex(index)
        menu = QMenu(self)
        delete = menu.addAction(QIcon.fromTheme("edit-delete"), DECK_VIEW["delete_unsorted"])
        name = index.data()
        delete.triggered.connect(lambda: self.discard_requested.emit(name))
        menu.exec(self.view.viewport().mapToGlobal(pos))
        menu.deleteLater()

    # -- files arriving -----------------------------------------------------

    def arriving(self, mime):
        """The dropped files that aren't already here"""
        folder = self.folder.resolve()
        return [path for path in local_files(mime) if Path(path).resolve().parent != folder]

    def dragEnterEvent(self, event):
        if self.arriving(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        files = self.arriving(event.mimeData())
        if not files:
            event.ignore()
            return
        event.acceptProposedAction()
        self.files_dropped.emit(files)
