"""Unassigned cards at the bottom of handmade decks"""

import os
from pathlib import Path

from PyQt6.QtCore import QEvent, QMimeData, QObject, QPoint, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPalette, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QLabel, QMenu, QVBoxLayout, QWidget

from tarot_canvas.models import staged_delete
from tarot_canvas.models.card_id_classifier import classify_card_id
from tarot_canvas.models.deck_writer import BACK, UNSORTED
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.activate_on_return import RETURN_KEYS, activate_on_return
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.dropped_files import dropped_files, offered_files
from tarot_canvas.ui.strings import DECK_VIEW, notes_text
from tarot_canvas.ui.widgets.inline_message import InlineMessage

PathRole = Qt.ItemDataRole.UserRole + 1
NameRole = Qt.ItemDataRole.UserRole + 2
CardIdRole = Qt.ItemDataRole.UserRole + 3  # the card ID its file name names, or None

# The file name, and under it the card it was classified as
TEXT_LINES = 2


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
        # The grid size holds the margins; spacing as well would leave room for one line of text
        self.setSpacing(0)
        # Each line, the file name then its card, elided on its own
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)


class _OnePressEach(QObject):
    """Swallows a held Return's repeats, so each image placed is a press of its own"""

    def eventFilter(self, _watched, event):
        return (
            event.type() == QEvent.Type.KeyPress
            and event.key() in RETURN_KEYS
            and event.isAutoRepeat()
        )


class UnsortedStrip(QWidget):
    # Local files dropped here
    files_dropped = pyqtSignal(list)
    discard_requested = pyqtSignal(str)  # a file name in unsorted/
    place_requested = pyqtSignal(str, str)  # an image's path, the card ID (or BACK) for it
    card_wanted = pyqtSignal(str, QPoint)  # an image's path, where to ask which card it is

    def __init__(self, deck, cover_size, parent=None):
        super().__init__(parent)
        self.deck = deck
        self.folder = Path(deck.root_path) / UNSORTED
        self._cover_size = cover_size
        self._covers = CoverCache(capacity=128)
        # Images on their way into a slot: still in unsorted/ until their turn in the editor's
        # queue, but no longer shown, so nothing can place one twice
        self._leaving = set()
        self.setAcceptDrops(True)

        heading = QLabel(DECK_VIEW["unsorted"])
        typography.apply(heading, typography.Role.HEADING_2)

        # A deleted image's Undo, here and not atop the page: Delete is pressed in this strip,
        # which may be scrolled far below the page's top
        self.message = InlineMessage(close_text=notes_text("dismiss"))

        self.empty_label = QLabel(DECK_VIEW["unsorted_empty"])
        self.empty_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.model = _UnsortedModel(self)
        self.view = UnsortedView()
        self.view.setModel(self.model)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        # Double-click or Return does what the menu's default would: place it as the card its
        # name names, or ask which card it is
        self.view.activated.connect(self._on_activated)
        activate_on_return(self.view)
        # Installed last, so it sees Return before the Mac's filter does
        self.view.installEventFilter(_OnePressEach(self.view))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addWidget(heading)
        layout.addWidget(self.message)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.view)
        self.reload()

    def names(self):
        return [self.model.item(row).data(NameRole) for row in range(self.model.rowCount())]

    def card_ids(self):
        return [self.model.item(row).data(CardIdRole) for row in range(self.model.rowCount())]

    def current_name(self):
        index = self.view.currentIndex()
        return index.data(NameRole) if index.isValid() else None

    def set_deck(self, deck):
        self.deck = deck
        self.reload()

    def card_name(self, card_id):
        if card_id == BACK:
            return DECK_VIEW["back"]
        card = self.deck.find_card(card_id)
        return card.display_name if card else card_id

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
                if entry.is_file()
                and not entry.name.startswith(".")
                and not staged_delete.is_staged(entry.name)
                and entry.path not in self._leaving
            ]
        except FileNotFoundError:
            entries = []
        size = QSize(self._cover_size)
        width, height = size.width(), size.height()
        self.view.setIconSize(size)
        line = QFontMetrics(self.view.font()).height()
        self.view.setGridSize(
            QSize(
                width + 2 * units.LARGE_SPACING,
                height + TEXT_LINES * line + 2 * units.LARGE_SPACING,
            )
        )
        dpr = self.devicePixelRatioF()
        for entry in sorted(entries, key=lambda entry: entry.name):
            card_id = classify_card_id(Path(entry.name).stem, self.deck)
            text = f"{entry.name}\n{self.card_name(card_id)}" if card_id else entry.name
            item = QStandardItem(text)
            item.setData(entry.path, PathRole)
            item.setData(entry.name, NameRole)
            item.setData(card_id, CardIdRole)
            item.setToolTip(text)
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
        self._show_empty(not entries)

    def _on_activated(self, index):
        if not index.isValid():
            return
        card_id = index.data(CardIdRole)
        if card_id:
            self.place_requested.emit(index.data(PathRole), card_id)
        else:
            self._want_card(index)

    def _want_card(self, index):
        rect = self.view.visualRect(index)
        where = self.view.viewport().mapToGlobal(rect.bottomLeft())
        self.card_wanted.emit(index.data(PathRole), where)

    def leave(self, path):
        """hide an image and make the next image current"""
        rows = [self.model.item(row).data(PathRole) for row in range(self.model.rowCount())]
        if path not in rows:
            return
        row = rows.index(path)
        if len(rows) > 1:
            step = row + 1 if row + 1 < len(rows) else row - 1
            self.view.setCurrentIndex(self.model.index(step, 0))
        self._leaving.add(path)
        self.model.removeRow(row)
        self._show_empty(self.model.rowCount() == 0)

    def settle(self):
        """The editor is idle so show unsorted/"""
        self._leaving.clear()

    def _show_empty(self, empty):
        self.empty_label.setVisible(empty)
        self.view.setVisible(not empty)

    def _on_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        self.view.setCurrentIndex(index)
        menu = self.item_menu(index)
        menu.exec(self.view.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def item_menu(self, index):
        menu = QMenu(self)
        path, card_id = index.data(PathRole), index.data(CardIdRole)
        if card_id:
            place = menu.addAction(
                QIcon.fromTheme("go-up"), DECK_VIEW["place_as"].format(card=self.card_name(card_id))
            )
            place.triggered.connect(lambda: self.place_requested.emit(path, card_id))
            menu.setDefaultAction(place)
        other = menu.addAction(QIcon.fromTheme("search"), DECK_VIEW["place_as_other"])
        other.triggered.connect(lambda: self._want_card(index))
        menu.addSeparator()
        delete = menu.addAction(QIcon.fromTheme("edit-delete"), DECK_VIEW["delete_unsorted"])
        name = index.data(NameRole)
        delete.triggered.connect(lambda: self.discard_requested.emit(name))
        return menu

    # -- files arriving -----------------------------------------------------

    def arriving(self, mime):
        """The files a drag offers that aren't already here"""
        return self.not_here(offered_files(mime))

    def not_here(self, paths):
        """paths, less those already in unsorted/"""
        folder = self.folder.resolve()
        return [path for path in paths if Path(path).resolve().parent != folder]

    def dragEnterEvent(self, event):
        if self.arriving(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if not self.arriving(event.mimeData()):
            event.ignore()
            return
        event.acceptProposedAction()
        files = self.not_here(dropped_files(event.mimeData()))
        if files:
            self.files_dropped.emit(files)
