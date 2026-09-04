"""Scaled, device-pixel-ratio-aware cover pixmaps, cached by request."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImageReader, QPixmap


class CoverCache:
    """Cache of cover pixmaps keyed by (path, well size, device pixel ratio).

    Decoding goes through `QImageReader.setScaledSize()` so a 2400px source is
    never fully decoded just to paint a 216px cell. A miss that fails to decode
    is cached as `None`, so a broken file is not retried on every repaint.
    """

    def __init__(self, capacity=256):
        self._capacity = capacity
        self._pixmaps = {}

    def clear(self):
        self._pixmaps.clear()

    def get(self, path, well_size, device_pixel_ratio=1.0):
        """Cover for `path` fitted inside `well_size`, or None if undecodable."""
        key = (path, well_size.width(), well_size.height(), round(device_pixel_ratio, 3))
        if key in self._pixmaps:
            return self._pixmaps[key]

        pixmap = self._decode(path, well_size, device_pixel_ratio)
        if len(self._pixmaps) >= self._capacity:
            self._pixmaps.clear()
        self._pixmaps[key] = pixmap
        return pixmap

    @staticmethod
    def _decode(path, well_size, device_pixel_ratio):
        if not path:
            return None

        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        source = reader.size()
        if not source.isValid() or source.isEmpty():
            return None

        # Fit inside the well in logical pixels, then decode at device pixels.
        target = source.scaled(well_size, Qt.AspectRatioMode.KeepAspectRatio)
        if target.isEmpty():
            return None
        device_target = QSize(
            max(1, round(target.width() * device_pixel_ratio)),
            max(1, round(target.height() * device_pixel_ratio)),
        )
        reader.setScaledSize(device_target)

        image = reader.read()
        if image.isNull():
            return None

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        return pixmap
