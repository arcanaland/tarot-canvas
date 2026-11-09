"""A picture as the canvas ground"""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QImageIOHandler,
    QImageReader,
    QPainter,
    QPixmap,
)

from tarot_canvas.utils.logger import logger

_last_load = None


def decode_bound():
    """The largest screen in device pixels"""
    bound = QSize(1, 1)
    for screen in QGuiApplication.screens():
        ratio = screen.devicePixelRatio()
        size = screen.geometry().size()
        bound = bound.expandedTo(QSize(round(size.width() * ratio), round(size.height() * ratio)))
    return bound


def _decode(path, positioning, bound):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    upright = reader.transformation() == QImageIOHandler.Transformation.TransformationNone
    if size.isValid() and upright:
        if positioning == "center":
            # Centered shows the image at its own size, so only the middle can be seen
            clip = QRect(QPoint(0, 0), size.boundedTo(bound))
            clip.moveCenter(QRect(QPoint(0, 0), size).center())
            reader.setClipRect(clip)
        elif size.width() > bound.width() and size.height() > bound.height():
            reader.setScaledSize(size.scaled(bound, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
    image = reader.read()
    if image.isNull():
        logger.warning(f"Could not decode the background {path}: {reader.errorString()}")
    return image


def load(path, positioning, bound):
    """The image at path decoded for positioning"""
    global _last_load
    try:
        stamp = path.stat().st_mtime_ns
    except OSError as error:
        logger.warning(f"The background {path} is missing: {error}")
        return QImage()
    mode = "center" if positioning == "center" else "scaled"
    key = (str(path), stamp, mode, bound.width(), bound.height())
    if _last_load is not None and _last_load[0] == key:
        return _last_load[1]
    image = _decode(path, positioning, bound)
    if not image.isNull():
        _last_load = (key, image)
    return image


def flatten(source, fill):
    """source laid on fill with no alpha"""
    if not source.hasAlphaChannel():
        return source
    image = QImage(source.size(), QImage.Format.Format_RGB32)
    image.fill(QColor(fill))
    painter = QPainter(image)
    painter.drawImage(QPoint(0, 0), source)
    painter.end()
    return image


def average_colour(image):
    return image.scaled(
        1, 1, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    ).pixelColor(0, 0)


def compose(source, size, positioning, fill):
    """A QImage of size device pixels, source placed on fill"""
    image = QImage(size, QImage.Format.Format_RGB32)
    image.fill(QColor(fill))
    target = QRect(QPoint(0, 0), size)
    if positioning == "stretch":
        placed = target.size()
    elif positioning == "fit":
        placed = source.size().scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
    elif positioning == "center":
        placed = source.size()
    else:
        placed = source.size().scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    rect = QRect(QPoint(0, 0), placed)
    rect.moveCenter(target.center())
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(rect, source)
    painter.end()
    return image


class ImageGround:
    """Paints source over the viewport"""

    def __init__(self, source, positioning, fill):
        self.source = source
        self.positioning = positioning
        self.fill = QColor(fill)
        self._key = None
        self._pixmap = None

    def paint(self, painter, rect, ratio):
        size = QSize(round(rect.width() * ratio), round(rect.height() * ratio))
        if size.isEmpty():
            return False
        key = (size.width(), size.height(), ratio)
        if key != self._key:
            self._pixmap = QPixmap.fromImage(
                compose(self.source, size, self.positioning, self.fill)
            )
            self._pixmap.setDevicePixelRatio(ratio)
            self._key = key
        painter.save()
        painter.resetTransform()
        painter.drawPixmap(QPoint(0, 0), self._pixmap)
        painter.restore()
        return True
