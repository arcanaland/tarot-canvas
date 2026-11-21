"""Scaled, device-pixel-ratio-aware cover pixmaps, cached by request."""

import os

from PyQt6.QtGui import QPixmap

from tarot_canvas.ui.canvas.detail import art_size, fit_device_size, read_art


class CoverCache:
    """Cache of cover pixmaps keyed by (path, mtime, well size, device pixel ratio)."""

    def __init__(self, capacity=256):
        self._capacity = capacity
        self._pixmaps = {}

    def clear(self):
        self._pixmaps.clear()

    def get(self, path, well_size, device_pixel_ratio=1.0):
        modified = modified_ns(path)
        if path and modified is None:
            return None
        key = (path, modified, well_size.width(), well_size.height(), round(device_pixel_ratio, 3))
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

        source = art_size(path)
        if not source.isValid() or source.isEmpty():
            return None

        size = fit_device_size(source, well_size, device_pixel_ratio)
        if size.isEmpty():
            return None
        image = read_art(str(path), size)
        if image.isNull():
            return None

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        return pixmap


def modified_ns(path):
    """path's st_mtime_ns, or None when there is no file"""
    try:
        return os.stat(path).st_mtime_ns
    except (OSError, TypeError, ValueError):
        return None
