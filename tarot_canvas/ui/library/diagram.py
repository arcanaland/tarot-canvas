"""A layout's shape with its numbers, for any Library view's pane; a reading's on its ground"""

from PyQt6.QtCore import QObject, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from tarot_canvas.models import backgrounds
from tarot_canvas.ui import units
from tarot_canvas.ui.canvas.detail import art_loader, art_size
from tarot_canvas.ui.canvas.ground_paint import paint_ground
from tarot_canvas.ui.canvas.tab_icon import DIAGRAM, GROUNDED_DIAGRAM, spread_icon

# (name, st_mtime_ns, device w, device h) -> an image ground's picture, decoded for a diagram
_sources = {}


def source_key(name, device):
    path = backgrounds.background_path(name)
    try:
        stamp = path.stat().st_mtime_ns if path is not None else None
    except OSError:
        stamp = None
    if stamp is None:
        return None
    return (name, stamp, device.width(), device.height())


class _PendingSource(QObject):
    """ArtLoader's receiver for one picture's decode. The diagram holds it until it lands."""

    def __init__(self, diagram, key):
        super().__init__(diagram)
        self.diagram = diagram
        self.key = key

    def receive_detail(self, _level, image):
        _sources[self.key] = image
        self.diagram.source_ready(self)


class LayoutDiagram(QWidget):
    """Marks as large as its width and the pane's height allow, over a ground or none"""

    WIDTH = 14 * units.GRID_UNIT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon = None
        self._ground = None
        self._pending = None
        self.setFixedWidth(self.WIDTH)
        self.hide()

    def ground(self):
        return self._ground

    def show_marks(self, marks, ground=None):
        """marks already through layout_marks; none hides it. ground is drawn()-resolved"""
        self._ground = ground if marks else None
        style = DIAGRAM if ground is None else GROUNDED_DIAGRAM
        self._icon = spread_icon(marks, style) if marks else None
        self.setVisible(self._icon is not None)
        self._request_source()
        self.update()

    def square(self):
        """Where the diagram paints: a square at the top, centred across"""
        side = min(self.width(), self.height())
        square = QRect(0, 0, side, side)
        square.moveCenter(QRect(0, 0, self.width(), side).center())
        return square

    def _device(self):
        ratio = self.devicePixelRatioF()
        side = self.square().width()
        return QSize(round(side * ratio), round(side * ratio))

    def _source_key(self):
        ground = self._ground
        device = self._device()
        if ground is None or ground.style != "image" or device.isEmpty():
            return None
        return source_key(ground.image, device)

    def _request_source(self):
        key = self._source_key()
        if key is None or key in _sources:
            return
        if self._pending is not None:
            if self._pending.key == key:
                return
            self._pending.deleteLater()
        path = backgrounds.background_path(self._ground.image)
        source = art_size(path)
        if not source.isValid() or source.isEmpty():
            self._pending = None
            return
        self._pending = _PendingSource(self, key)
        decode = source.scaled(QSize(key[2], key[3]), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        art_loader().request(self._pending, str(path), decode, 0)

    def source_ready(self, request):
        """A decode landed; cached either way, painted only if still the one wanted"""
        if request is not self._pending:
            return
        self._pending = None
        request.deleteLater()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._request_source()

    def paintEvent(self, event):
        if self._icon is None:
            return
        square = self.square()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._ground is not None:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(square), units.COVER_RADIUS, units.COVER_RADIUS)
            painter.setClipPath(clip)
            image = _sources.get(self._source_key())
            paint_ground(painter, square, self._ground, self.devicePixelRatioF(), image)
            painter.restore()
        self._icon.paint(painter, square)
        painter.end()
