"""The Background page's tiles of the images a ground can be"""

from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QIcon,
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
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QToolTip,
)

from tarot_canvas.models import backgrounds
from tarot_canvas.ui.canvas.detail import art_loader, art_size
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well
from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.strings import PREFERENCES
from tarot_canvas.utils.logger import logger

NAME_ROLE = Qt.ItemDataRole.UserRole
PENDING_ROLE = Qt.ItemDataRole.UserRole + 1

TILE_WIDTH = 8 * units.GRID_UNIT
# A strip's tiles, small enough that a panel's width shows a few
STRIP_TILE_WIDTH = 4 * units.GRID_UNIT
ACTION_SIZE = units.GRID_UNIT + units.SMALL_SPACING
PENDING_OPACITY = 0.35
SELECTION_WIDTH = 3

OPEN_FOLDER = "open_folder"
REMOVE = "remove"


# Thumbnails already cut, by (path, mtime, device width, device height): a reopened
# dialog shows them at once
_thumbnails = {}


def thumbnail_key(path, device):
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return None
    return (str(path), stamp, device.width(), device.height())


def crop_thumbnail(image, device, ratio):
    """A decode at least device in both directions, cropped to device about its centre"""
    crop = QRect(QPoint(0, 0), device)
    crop.moveCenter(image.rect().center())
    pixmap = QPixmap.fromImage(image.copy(crop))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


class _PendingThumbnail(QObject):
    """ArtLoader's receiver for one tile's decode. The grid holds it until it lands."""

    def __init__(self, grid, name, key, device, ratio):
        super().__init__(grid)
        self.grid = grid
        self.name = name
        self.key = key
        self.device = device
        self.ratio = ratio

    def receive_detail(self, _level, image):
        pixmap = crop_thumbnail(image, self.device, self.ratio)
        _thumbnails[self.key] = pixmap
        self.grid.thumbnail_ready(self, pixmap)


class BackgroundDelegate(QStyledItemDelegate):
    def __init__(self, tile, actions=True, parent=None):
        super().__init__(parent)
        self.tile = tile
        # Whether a tile offers Remove and Open Folder
        self.actions = actions

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
        if not self.actions:
            return rects
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
        else:
            # Still decoding
            paint_placeholder_well(painter, tile, palette)
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

    def __init__(self, aspect, tile_actions=True, strip=False, parent=None):
        """tile_actions: whether the tiles offer Remove and Open Folder.
        strip: one row of tiles, scrolling sideways, rather than rows that wrap."""
        super().__init__(parent)
        width = STRIP_TILE_WIDTH if strip else TILE_WIDTH
        tile = QSize(width, round(width / aspect))
        self.tile_actions = tile_actions
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
        self.delegate = BackgroundDelegate(tile, tile_actions, self)
        self.setItemDelegate(self.delegate)
        # Decodes in flight, by name
        self._pending = {}
        if strip:
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(False)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            cell = self.delegate.sizeHint(None, None).height() + 2 * self.spacing()
            scroll = self.horizontalScrollBar().sizeHint().height()
            self.setFixedHeight(cell + scroll + 2 * self.frameWidth())
            # As wide as the rows around it, which it scrolls within
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def reload(self, pending=()):
        """Re-read the backgrounds directory, keeping the selection and the pending removals.

        Rows are added at once; a thumbnail not cut before is decoded off the GUI thread and
        fills its tile when it lands.
        """
        selected = self.selected_name()
        self.model_.clear()
        for request in self._pending.values():
            request.deleteLater()
        self._pending.clear()
        ratio = self.devicePixelRatioF()
        tile = self.delegate.tile
        device = QSize(round(tile.width() * ratio), round(tile.height() * ratio))
        for name in backgrounds.list_backgrounds():
            path = backgrounds.background_path(name)
            # The header only: cheap, and enough to leave out what can't be read
            source = art_size(path)
            key = thumbnail_key(path, device)
            if not source.isValid() or source.isEmpty() or key is None:
                logger.warning(f"Leaving the undecodable background {name} out of the grid")
                continue
            item = QStandardItem()
            item.setData(name, NAME_ROLE)
            item.setData(name in pending, PENDING_ROLE)
            cached = _thumbnails.get(key)
            if cached is not None:
                item.setData(cached, Qt.ItemDataRole.DecorationRole)
            else:
                request = _PendingThumbnail(self, name, key, device, ratio)
                self._pending[name] = request
                decode = source.scaled(device, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                art_loader().request(request, str(path), decode, 0)
            item.setEditable(False)
            item.setDropEnabled(False)
            self.model_.appendRow(item)
        self.select_name(selected)

    def thumbnail_ready(self, request, pixmap):
        if self._pending.get(request.name) is not request:
            return
        del self._pending[request.name]
        request.deleteLater()
        row = self._row_of(request.name)
        if row >= 0:
            self.model_.item(row).setData(pixmap, Qt.ItemDataRole.DecorationRole)

    def is_loading(self):
        return bool(self._pending)

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
        if self.tile_actions and event.key() == Qt.Key.Key_Delete and self.currentIndex().isValid():
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
