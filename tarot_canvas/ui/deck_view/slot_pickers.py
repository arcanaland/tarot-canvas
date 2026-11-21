"""Popups for choosing an unassigned image for a card"""

import math

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from tarot_canvas.models.card_search import CardTerms, Query
from tarot_canvas.models.deck_writer import BACK
from tarot_canvas.ui import units
from tarot_canvas.ui.activate_on_return import RETURN_KEYS
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.widgets.search_field import search_field

IMAGE_COLUMNS = 4
IMAGE_ROWS = 2
CARD_ROWS = 12

SlotRole = Qt.ItemDataRole.UserRole + 1


class _Popup(QFrame):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFrameShape(QFrame.Shape.StyledPanel)

    def show_at(self, global_point):
        """Shown with its top left at global_point, kept on that point's screen"""
        self.adjustSize()
        screen = self.screen() if self.parentWidget() is None else self.parentWidget().screen()
        area = screen.availableGeometry()
        x = min(max(global_point.x(), area.left()), area.right() - self.width())
        y = global_point.y()
        if y + self.height() > area.bottom():
            y = max(area.top(), area.bottom() - self.height())
        self.move(QPoint(x, y))
        self.show()


class ImagePicker(_Popup):
    """Popup that shows up when pressing + on card when there are unassigned images"""

    image_chosen = pyqtSignal(str)  # the image's path
    file_requested = pyqtSignal()

    def __init__(self, model, path_role, icon_size, grid_size, parent=None):
        super().__init__(parent)
        self.setAccessibleName(DECK_VIEW["image_picker_name"])
        self._path_role = path_role

        self.view = QListView()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setWrapping(True)
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setModel(model)
        self.view.setIconSize(icon_size)
        self.view.setGridSize(grid_size)
        # Picks on one click, as a menu does
        self.view.clicked.connect(self._pick)
        self.view.installEventFilter(self)

        self.view.setSpacing(0)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        count = model.rowCount()
        columns = max(1, min(count, IMAGE_COLUMNS))
        rows = max(1, min(math.ceil(count / columns), IMAGE_ROWS))
        # Room for the scroll bar always, or showing it would wrap a column away
        scroll = self.view.verticalScrollBar().sizeHint().width()
        slack = 2 * units.SMALL_SPACING
        self.view.setFixedSize(
            QSize(
                columns * grid_size.width() + scroll + slack,
                rows * grid_size.height() + slack,
            )
        )
        self.view.setCurrentIndex(model.index(0, 0))

        self.from_file = QPushButton(QIcon.fromTheme("document-open"), DECK_VIEW["from_file"])
        self.from_file.setFlat(True)
        self.from_file.clicked.connect(self._from_file)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*(units.SMALL_SPACING,) * 4)
        layout.setSpacing(units.SMALL_SPACING)
        layout.addWidget(self.view)
        layout.addWidget(self.from_file, 0, Qt.AlignmentFlag.AlignLeft)
        self.setFocusProxy(self.view)

    def eventFilter(self, watched, event):
        if (
            watched is self.view
            and event.type() == QEvent.Type.KeyPress
            and event.key() in RETURN_KEYS
        ):
            self._pick(self.view.currentIndex())
            return True
        return False

    def _pick(self, index):
        if not index.isValid():
            return
        path = index.data(self._path_role)
        self.close()
        self.image_chosen.emit(path)

    def _from_file(self):
        self.close()
        self.file_requested.emit()


class CardPicker(_Popup):
    """The deck's slots, found by typing, for one image"""

    card_chosen = pyqtSignal(str)  # card ID, or BACK

    def __init__(self, deck, parent=None):
        super().__init__(parent)
        self.setAccessibleName(DECK_VIEW["card_picker_name"])

        self.find = search_field(DECK_VIEW["find_card"])
        self.find.textChanged.connect(self._filter)
        self.find.installEventFilter(self)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.itemClicked.connect(self._pick)
        self.list.installEventFilter(self)
        self._terms = []
        for card in deck.cards:
            item = QListWidgetItem(card.display_name)
            item.setData(SlotRole, card.canonical_id)
            self.list.addItem(item)
            self._terms.append(CardTerms(card, deck.metadata.name))
        back = QListWidgetItem(DECK_VIEW["back"])
        back.setData(SlotRole, BACK)
        self.list.addItem(back)
        self._terms.append(None)

        row = self.list.sizeHintForRow(0) if self.list.count() else units.GRID_UNIT
        self.list.setFixedHeight(row * CARD_ROWS + 2)
        self.list.setMinimumWidth(self.list.sizeHintForColumn(0) + 4 * units.GRID_UNIT)
        self.list.setCurrentRow(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*(units.SMALL_SPACING,) * 4)
        layout.setSpacing(units.SMALL_SPACING)
        layout.addWidget(self.find)
        layout.addWidget(self.list)
        self.setFocusProxy(self.find)

    def visible_slots(self):
        return [
            self.list.item(row).data(SlotRole)
            for row in range(self.list.count())
            if not self.list.item(row).isHidden()
        ]

    def _filter(self, text):
        query = Query(text)
        for row, terms in enumerate(self._terms):
            item = self.list.item(row)
            if terms is None:
                found = not query or query.text in item.text().casefold()
            else:
                found = terms.tier(query) is not None
            item.setHidden(not found)
        current = self.list.currentItem()
        if current is None or current.isHidden():
            first = next(
                (row for row in range(self.list.count()) if not self.list.item(row).isHidden()),
                None,
            )
            self.list.setCurrentRow(first if first is not None else -1)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if key in RETURN_KEYS:
            self._pick(self.list.currentItem())
            return True
        if watched is self.find and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._step(-1 if key == Qt.Key.Key_Up else 1)
            return True
        return False

    def _step(self, direction):
        row = self.list.currentRow() + direction
        while 0 <= row < self.list.count():
            if not self.list.item(row).isHidden():
                self.list.setCurrentRow(row)
                return
            row += direction

    def _pick(self, item):
        if item is None or item.isHidden():
            return
        slot = item.data(SlotRole)
        self.close()
        self.card_chosen.emit(slot)
