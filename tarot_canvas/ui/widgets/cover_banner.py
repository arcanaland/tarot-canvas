"""A deck's cover blurred into a band of colour, for a heading to sit on"""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QImageReader, QPainter, QPalette, QPixmap

from tarot_canvas.ui.library import units

BANNER_PADDING = 2 * units.LARGE_SPACING
BANNER_SAMPLE_WIDTH = 24
BANNER_SCRIM_ALPHA = 165
BANNER_TEXT = QColor(255, 255, 255)
BANNER_SUBTEXT = QColor(255, 255, 255, 190)
BANNER_OUTLINE = QColor(255, 255, 255, 64)


class CoverBanner:
    """Banners cached by (cover path, size, device pixel ratio)"""

    def __init__(self, capacity=16):
        self._capacity = capacity
        self._pixmaps = {}

    def pixmap(self, path, size, ratio):
        key = (path, size.width(), size.height(), round(ratio, 3))
        if key not in self._pixmaps:
            if len(self._pixmaps) >= self._capacity:
                self._pixmaps.clear()
            self._pixmaps[key] = render_banner(path, size, ratio)
        return self._pixmaps[key]

    def paint(self, painter, rect, path, ratio):
        """The band over `rect`, with its hairline; nothing if the cover can't be read"""
        pixmap = self.pixmap(path, rect.size(), ratio)
        if pixmap is None:
            return
        painter.drawPixmap(rect, pixmap)
        painter.setPen(BANNER_OUTLINE)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())


def is_readable_cover(path):
    return bool(path) and QImageReader(str(path)).size().isValid()


def render_banner(path, size, ratio):
    """The cover, blurred and scrimmed, filling `size`. None if it cannot be read."""
    if not path or size.isEmpty():
        return None

    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source = reader.size()
    if not source.isValid() or source.isEmpty():
        return None

    height = max(1, round(BANNER_SAMPLE_WIDTH * source.height() / source.width()))
    reader.setScaledSize(QSize(BANNER_SAMPLE_WIDTH, height))
    image = reader.read()
    if image.isNull():
        return None

    # upscale the tiny decode smoothly (blur)
    device = QSize(max(1, round(size.width() * ratio)), max(1, round(size.height() * ratio)))
    image = image.scaled(
        device,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    offset = QPoint(
        max(0, (image.width() - device.width()) // 2),
        max(0, (image.height() - device.height()) // 2),
    )

    image = image.copy(QRect(offset, device))

    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)

    painter = QPainter(pixmap)
    painter.fillRect(pixmap.rect(), QColor(0, 0, 0, BANNER_SCRIM_ALPHA))
    painter.end()
    return pixmap


def set_banner_text(label, on_banner, colour, role):
    """Light `colour` while the label sits on a banner, the palette's `role` otherwise"""
    if on_banner:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.WindowText, colour)
        label.setForegroundRole(QPalette.ColorRole.WindowText)
        label.setPalette(palette)
    else:
        label.setPalette(QPalette())
        label.setForegroundRole(role)
