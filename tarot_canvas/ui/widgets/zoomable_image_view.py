from contextlib import contextmanager

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QSizePolicy,
)

# Zoom is expressed in multiples of native scale
MAX_NATIVE_ZOOM = 4.0
WHEEL_ZOOM_FACTOR = 1.15
KEY_ZOOM_FACTOR = 1.25

_SCALE_EPSILON = 1e-3


class ZoomableImageView(QGraphicsView):
    """A pan/zoom view of a single image"""

    # The scale changed, or the image did
    zoom_changed = pyqtSignal()
    # Left or Right with nothing to pan: -1 for the previous image, 1 for the next
    step_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        self._at_fit = True
        self._pan_button = None
        self._last_mouse_pos = None

        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(1, 1)

    # -- content ---------------------------------------------------------

    def set_pixmap(self, pixmap):
        """Show pixmap at fit. A null or missing pixmap clears the view."""
        self._scene.clear()  # drops any previous item
        self._pixmap_item = None
        if pixmap is None or pixmap.isNull():
            self._scene.setSceneRect(QRectF())
            self.resetTransform()
            self.zoom_changed.emit()
            return
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.reset_to_fit()

    def set_message(self, text):
        """Show text in place of an image (no image available, load failure)."""
        self._scene.clear()
        self._pixmap_item = None
        item = QGraphicsSimpleTextItem(text)
        item.setBrush(self.palette().windowText())
        self._scene.addItem(item)
        self._scene.setSceneRect(item.boundingRect())
        self.resetTransform()
        self.centerOn(item)
        self.zoom_changed.emit()

    def has_image(self):
        return self._pixmap_item is not None

    def pixmap(self):
        return self._pixmap_item.pixmap() if self._pixmap_item else QPixmap()

    # -- scales ----------------------------------------------------------

    def device_pixel_ratio(self):
        return self.viewport().devicePixelRatioF() or 1.0

    def native_scale(self):
        """View scale at which one source pixel covers one device pixel."""
        return 1.0 / self.device_pixel_ratio()

    def fit_scale(self):
        """View scale at which the whole image is just inside the viewport."""
        if not self._pixmap_item:
            return 1.0
        source = self._pixmap_item.boundingRect()
        viewport = self.viewport().rect()
        if source.isEmpty() or viewport.isEmpty():
            return 1.0
        return min(viewport.width() / source.width(), viewport.height() / source.height())

    def current_scale(self):
        return self.transform().m11()

    def min_scale(self):
        return self.fit_scale()

    def max_scale(self):
        return max(self.fit_scale(), MAX_NATIVE_ZOOM * self.native_scale())

    def is_at_fit(self):
        return abs(self.current_scale() - self.fit_scale()) <= _SCALE_EPSILON * self.fit_scale()

    # -- geometry --------------------------------------------------------

    # Breathing room for widget beside the artwork
    BAND_MARGIN = 16

    def image_viewport_rect(self):
        if not self._pixmap_item:
            return QRect()
        return self.mapFromScene(self._pixmap_item.sceneBoundingRect()).boundingRect()

    def clear_band_position(self, size):
        """Where the widget goes"""
        image = self.image_viewport_rect()
        if image.isEmpty():
            return None
        viewport = self.viewport().rect()
        left = QRect(viewport.left(), viewport.top(), image.left() - viewport.left(), 0)
        right = QRect(image.right(), viewport.top(), viewport.right() - image.right(), 0)

        # Prefer the trailing band
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        needed = size.width() + 2 * self.BAND_MARGIN
        for band in (left, right) if rtl else (right, left):
            if band.width() >= needed:
                return QPoint(
                    band.left() + (band.width() - size.width()) // 2,
                    viewport.top() + (viewport.height() - size.height()) // 2,
                )
        return None

    # -- zooming ---------------------------------------------------------

    @contextmanager
    def _anchored_to_center(self):
        previous = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        try:
            yield
        finally:
            self.setTransformationAnchor(previous)

    def zoom_to(self, scale):
        """Scale to `scale`, clamped to [fit, 4x native], about the current anchor."""
        if not self._pixmap_item:
            return
        scale = max(self.min_scale(), min(self.max_scale(), scale))
        current = self.current_scale()
        if abs(scale - current) <= _SCALE_EPSILON * current:
            return
        self.scale(scale / current, scale / current)
        self._at_fit = self.is_at_fit()
        self.zoom_changed.emit()

    def zoom_by(self, factor):
        self.zoom_to(self.current_scale() * factor)

    def zoom_in(self):
        with self._anchored_to_center():
            self.zoom_by(KEY_ZOOM_FACTOR)

    def zoom_out(self):
        with self._anchored_to_center():
            self.zoom_by(1.0 / KEY_ZOOM_FACTOR)

    def reset_to_fit(self):
        """Frame the whole image"""
        self._at_fit = True
        if not self._pixmap_item:
            return
        scale = self.fit_scale()
        self.setTransform(QTransform().scale(scale, scale))
        self.centerOn(self._pixmap_item)
        self.zoom_changed.emit()

    def zoom_to_native(self):
        """100%: one source pixel per device pixel."""
        with self._anchored_to_center():
            self.zoom_to(self.native_scale())

    def toggle_fit_and_native(self):
        if self.is_at_fit():
            self.zoom_to(self.native_scale())
        else:
            self.reset_to_fit()

    def can_pan(self):
        return self.has_image() and not self.is_at_fit()

    # -- events ----------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._at_fit:
            self.reset_to_fit()
        else:
            # fit is the floor, and it just moved
            with self._anchored_to_center():
                self.zoom_to(self.current_scale())

    def showEvent(self, event):
        super().showEvent(event)
        if self._at_fit:
            self.reset_to_fit()

    def wheelEvent(self, event):
        """Bare wheel zooms, anchored under the pointer."""
        if not self._pixmap_item:
            return
        if event.angleDelta().y() > 0:
            self.zoom_by(WHEEL_ZOOM_FACTOR)
        else:
            self.zoom_by(1.0 / WHEEL_ZOOM_FACTOR)
        self._update_cursor()
        event.accept()

    def keyPressEvent(self, event):
        """Left and Right pan a zoomed image, and otherwise ask for its neighbour"""
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if step and not self.can_pan():
            self.step_requested.emit(step)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item:
            self.toggle_fit_and_native()
            self._update_cursor()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        starts_pan = event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)
        if self._pan_button is None and starts_pan and self.can_pan():
            self._pan_button = event.button()
            self._last_mouse_pos = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_button is not None and self._last_mouse_pos is not None:
            pos = event.position().toPoint()
            delta = pos - self._last_mouse_pos
            self._last_mouse_pos = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == self._pan_button:
            self._pan_button = None
            self._last_mouse_pos = None
            self._update_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_cursor(self):
        if self.can_pan():
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.viewport().unsetCursor()
