"""A layout's shape with its numbers, for any Library view's pane; a reading's on its ground"""

import math

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


def marks_extent(marks, style):
    """The fraction of a style's icon square that marks cover, turned as they are"""
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for mark in marks:
        radians = math.radians(mark.angle)
        cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
        half_w = (mark.w * cos + mark.h * sin) / 2
        half_h = (mark.w * sin + mark.h * cos) / 2
        x0, x1 = min(x0, mark.x - half_w), max(x1, mark.x + half_w)
        y0, y1 = min(y0, mark.y - half_h), max(y1, mark.y + half_h)
    area = 1 - 2 * style.inset
    return QRectF(
        style.inset + x0 * area, style.inset + y0 * area, (x1 - x0) * area, (y1 - y0) * area
    )


class LayoutDiagram(QWidget):
    """Marks as large as its width and the pane's height allow, over a ground or none.

    As a strip, the ground is cut to the marks' own extent with a margin round them, and the
    widget is as large as that, inside `strip`, allows.
    """

    WIDTH = 14 * units.GRID_UNIT
    STRIP_MARGIN = units.GRID_UNIT

    def __init__(self, parent=None, strip=None):
        super().__init__(parent)
        self._icon = None
        self._ground = None
        self._pending = None
        self._strip = strip  # the largest QSize a strip may take, or None for a square
        self._icon_rect = QRect()
        if strip is None:
            self.setFixedWidth(self.WIDTH)
        self.hide()

    def ground(self):
        return self._ground

    def show_marks(self, marks, ground=None):
        """marks already through layout_marks; none hides it. ground is drawn()-resolved"""
        self._ground = ground if marks else None
        style = DIAGRAM if ground is None else GROUNDED_DIAGRAM
        self._icon = spread_icon(marks, style) if marks else None
        if marks and self._strip is not None:
            self._fit_strip(marks, style)
        self.setVisible(self._icon is not None)
        self._request_source()
        self.update()

    def _fit_strip(self, marks, style):
        extent = marks_extent(marks, style)
        margin = self.STRIP_MARGIN
        span_w = max(extent.width(), 1e-3)
        span_h = max(extent.height(), 1e-3)
        side = min(
            (self._strip.width() - 2 * margin) / span_w,
            (self._strip.height() - 2 * margin) / span_h,
        )
        self.setFixedSize(round(span_w * side + 2 * margin), round(span_h * side + 2 * margin))
        self._icon_rect = QRect(
            round(margin - extent.x() * side),
            round(margin - extent.y() * side),
            round(side),
            round(side),
        )

    def square(self):
        """Where the ground paints: a square at the top, centred across, or a strip's whole rect"""
        if self._strip is not None:
            return self.rect()
        side = min(self.width(), self.height())
        square = QRect(0, 0, side, side)
        square.moveCenter(QRect(0, 0, self.width(), side).center())
        return square

    def icon_rect(self):
        """Where the marks' icon paints: the square, or the strip's square reaching past it"""
        return self._icon_rect if self._strip is not None else self.square()

    def _device(self):
        ratio = self.devicePixelRatioF()
        rect = self.square()
        return QSize(round(rect.width() * ratio), round(rect.height() * ratio))

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
        self._icon.paint(painter, self.icon_rect())
        painter.end()
