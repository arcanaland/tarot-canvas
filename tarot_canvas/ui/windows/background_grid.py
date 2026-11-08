"""The Background page's tiles of the images a ground can be"""

from PyQt6.QtCore import QEvent, QItemSelectionModel, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QImageReader,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QToolTip,
)

from tarot_canvas.models import backgrounds
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.strings import PREFERENCES
from tarot_canvas.utils.logger import logger

NAME_ROLE = Qt.ItemDataRole.UserRole
PENDING_ROLE = Qt.ItemDataRole.UserRole + 1

TILE_WIDTH = 8 * units.GRID_UNIT
ACTION_SIZE = units.GRID_UNIT + units.SMALL_SPACING
PENDING_OPACITY = 0.35
SELECTION_WIDTH = 3

OPEN_FOLDER = "open_folder"
REMOVE = "remove"


def thumbnail(path, size, ratio):
    """The image at path scaled and cropped to size, or a null pixmap"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    device = QSize(round(size.width() * ratio), round(size.height() * ratio))
    source = reader.size()
    if source.isValid():
        reader.setScaledSize(source.scaled(device, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    image = reader.read()
    if image.isNull():
        return QPixmap()
    image = image.scaled(
        device,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    crop = QRect(QPoint(0, 0), device)
    crop.moveCenter(image.rect().center())
    pixmap = QPixmap.fromImage(image.copy(crop))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class BackgroundDelegate(QStyledItemDelegate):
    def __init__(self, tile, parent=None):
        super().__init__(parent)
        self.tile = tile

    def sizeHint(self, option, index):
        return self.tile + QSize(2 * units.SMALL_SPACING, 2 * units.SMALL_SPACING)

    def tile_rect(self, cell):
        rect = QRect(QPoint(0, 0), self.tile)
        rect.moveCenter(cell.center())
        return rect

    def action_rects(self, cell, pending):
        """(action, rect) of a tile's buttons, from its top-right corner inward"""
        tile = self.tile_rect(cell)
        top = tile.top() + units.SMALL_SPACING
        right = tile.right() - units.SMALL_SPACING
        rects = []
        actions = (REMOVE,) if pending else (REMOVE, OPEN_FOLDER)
        for action in actions:
            rect = QRect(right - ACTION_SIZE + 1, top, ACTION_SIZE, ACTION_SIZE)
            rects.append((action, rect))
            right = rect.left() - units.SMALL_SPACING
        return rects

    @staticmethod
    def action_icon(action, pending):
        if action == OPEN_FOLDER:
            return QIcon.fromTheme("document-open-folder")
        return QIcon.fromTheme("edit-undo" if pending else "edit-delete")

    @staticmethod
    def action_tooltip(action, pending):
        if action == OPEN_FOLDER:
            return PREFERENCES["background_open_folder"]
        return PREFERENCES["background_undo_remove" if pending else "background_remove"]

    def paint(self, painter, option, index):
        palette = option.palette
        tile = self.tile_rect(option.rect)
        pending = bool(index.data(PENDING_ROLE))
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(tile), units.COVER_RADIUS, units.COVER_RADIUS)
        painter.setClipPath(clip)
        if pending:
            painter.setOpacity(PENDING_OPACITY)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            painter.drawPixmap(tile, pixmap)
        painter.setOpacity(1.0)
        painter.setClipping(False)

        if selected:
            pen = QPen(palette.highlight().color(), SELECTION_WIDTH)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = SELECTION_WIDTH / 2
            painter.drawRoundedRect(
                QRectF(tile).adjusted(-inset, -inset, inset, inset),
                units.COVER_RADIUS + inset,
                units.COVER_RADIUS + inset,
            )

        if hovered or pending:
            for action, rect in self.action_rects(option.rect, pending):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(palette.button())
                painter.drawEllipse(QRectF(rect))
                inner = rect.adjusted(
                    units.SMALL_SPACING,
                    units.SMALL_SPACING,
                    -units.SMALL_SPACING,
                    -units.SMALL_SPACING,
                )
                self.action_icon(action, pending).paint(painter, inner)
        painter.restore()

    def action_at(self, cell, index, pos):
        pending = bool(index.data(PENDING_ROLE))
        for action, rect in self.action_rects(cell, pending):
            if rect.contains(pos):
                return action
        return None

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            pending = bool(index.data(PENDING_ROLE))
            action = self.action_at(option.rect, index, event.pos())
            text = self.action_tooltip(action, pending) if action else index.data(NAME_ROLE)
            QToolTip.showText(event.globalPos(), text, view)
            return True
        return super().helpEvent(event, view, option, index)


class BackgroundGrid(QListView):
    """One tile per copied image; the selected tile is the ground"""

    # Local files dropped on the grid
    files_dropped = pyqtSignal(list)
    # The tile's name, after its pending removal was set or undone
    removal_toggled = pyqtSignal(str)
    open_folder_requested = pyqtSignal()

    def __init__(self, aspect, parent=None):
        super().__init__(parent)
        tile = QSize(TILE_WIDTH, round(TILE_WIDTH / aspect))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(units.SMALL_SPACING)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

        self.model_ = QStandardItemModel(self)
        self.setModel(self.model_)
        self.delegate = BackgroundDelegate(tile, self)
        self.setItemDelegate(self.delegate)

    def reload(self, pending=()):
        """Re-read the backgrounds directory, keeping the selection and the pending removals"""
        selected = self.selected_name()
        self.model_.clear()
        ratio = self.devicePixelRatioF()
        for name in backgrounds.list_backgrounds():
            pixmap = thumbnail(backgrounds.background_path(name), self.delegate.tile, ratio)
            if pixmap.isNull():
                logger.warning(f"Leaving the undecodable background {name} out of the grid")
                continue
            item = QStandardItem()
            item.setData(name, NAME_ROLE)
            item.setData(pixmap, Qt.ItemDataRole.DecorationRole)
            item.setData(name in pending, PENDING_ROLE)
            item.setEditable(False)
            item.setDropEnabled(False)
            self.model_.appendRow(item)
        self.select_name(selected)

    def names(self):
        return [self.model_.item(row).data(NAME_ROLE) for row in range(self.model_.rowCount())]

    def _row_of(self, name):
        for row in range(self.model_.rowCount()):
            if self.model_.item(row).data(NAME_ROLE) == name:
                return row
        return -1

    def selected_name(self):
        indexes = self.selectionModel().selectedIndexes() if self.selectionModel() else []
        return indexes[0].data(NAME_ROLE) if indexes else ""

    def select_name(self, name):
        row = self._row_of(name) if name else -1
        if row < 0 or self.is_pending(name):
            self.clearSelection()
            return
        index = self.model_.index(row, 0)
        self.setCurrentIndex(index)
        self.scrollTo(index)

    def is_pending(self, name):
        row = self._row_of(name)
        return row >= 0 and bool(self.model_.item(row).data(PENDING_ROLE))

    def pending(self):
        return tuple(name for name in self.names() if self.is_pending(name))

    def toggle_removal(self, name):
        """Mark name for removal, or undo that; the selection moves off a marked tile"""
        row = self._row_of(name)
        if row < 0:
            return
        item = self.model_.item(row)
        pending = not item.data(PENDING_ROLE)
        item.setData(pending, PENDING_ROLE)
        if pending and self.selected_name() == name:
            following = self.names()[row + 1 :] + self.names()[:row]
            self.select_name(next((n for n in following if not self.is_pending(n)), ""))
        self.removal_toggled.emit(name)

    def action_at(self, pos):
        """(action, name) of the tile button under pos, or (None, None)"""
        index = self.indexAt(pos)
        if not index.isValid():
            return None, None
        action = self.delegate.action_at(self.visualRect(index), index, pos)
        return action, index.data(NAME_ROLE) if action else None

    def trigger(self, action, name):
        if action == OPEN_FOLDER:
            self.open_folder_requested.emit()
        elif action == REMOVE:
            self.toggle_removal(name)

    def mousePressEvent(self, event):
        action, _name = self.action_at(event.position().toPoint())
        if action is not None:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        action, name = self.action_at(event.position().toPoint())
        if action is not None and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.trigger(action, name)
            return
        super().mouseReleaseEvent(event)

    def selectionCommand(self, index, event=None):
        if index.isValid() and index.data(PENDING_ROLE):
            return QItemSelectionModel.SelectionFlag.NoUpdate
        return super().selectionCommand(index, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.currentIndex().isValid():
            self.toggle_removal(self.currentIndex().data(NAME_ROLE))
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.model_.rowCount():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(muted_text(self.palette())))
        painter.drawText(
            self.viewport().rect(),
            Qt.AlignmentFlag.AlignCenter,
            PREFERENCES["background_drop_hint"],
        )
        painter.end()

    @staticmethod
    def _local_files(event):
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    def dragEnterEvent(self, event):
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = self._local_files(event)
        if not files:
            event.ignore()
            return
        event.acceptProposedAction()
        self.files_dropped.emit(files)
