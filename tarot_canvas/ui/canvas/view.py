from contextlib import contextmanager

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsView

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0


class PannableGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pan_button = None
        self._last_mouse_pos = None
        self._pointer_pos = None

    def pointer_scene_pos(self):
        """Scene position of the pointer, or None when it is not over the canvas.

        Tracked from the events themselves rather than read from QCursor.pos(), which
        on Wayland is only ever the last position Qt happened to observe.
        """
        if self._pointer_pos is None:
            return None
        return self.mapToScene(self._pointer_pos)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Enter:
            self._pointer_pos = event.position().toPoint()
        elif event.type() == QEvent.Type.Leave:
            self._pointer_pos = None
        return super().viewportEvent(event)

    def _visible_scene_rect(self):
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def grow_scene_rect(self):
        """Keep a viewport of scroll headroom around the camera in every direction.

        QGraphicsView derives its scrollbar range from the scene rect, so panning by
        scrollbar can never leave it. Recomputing the rect as (items | visible) plus a
        viewport-sized margin is how a free camera is expressed in Qt: the wall keeps
        moving ahead of the camera, and cards dragged outside stay reachable.
        """
        visible = self._visible_scene_rect()
        rect = self.scene().itemsBoundingRect().united(visible)
        rect.adjust(-visible.width(), -visible.height(), visible.width(), visible.height())
        self.scene().setSceneRect(rect)

    @contextmanager
    def _anchored_to_center(self):
        """Zoom about the viewport centre instead of the pointer.

        For zooms the pointer has nothing to do with — the toolbar buttons, whose
        cursor is off the canvas entirely, and the clamp that follows fitInView.
        """
        previous = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        try:
            yield
        finally:
            self.setTransformationAnchor(previous)

    def _scale_to(self, target):
        """Scale so the view ends at target, clamped to [MIN_ZOOM, MAX_ZOOM]."""
        current = self.transform().m11()
        target = max(MIN_ZOOM, min(MAX_ZOOM, target))
        if target != current:
            self.scale(target / current, target / current)
            self.grow_scene_rect()

    def zoom_by(self, factor):
        """Scale the view by factor about the pointer, clamped."""
        self._scale_to(self.transform().m11() * factor)

    def zoom_by_from_center(self, factor):
        """Scale the view by factor about the viewport centre, clamped."""
        with self._anchored_to_center():
            self._scale_to(self.transform().m11() * factor)

    def fit_to_rect(self, rect):
        """Frame rect, keeping the resulting zoom inside the clamp.

        fitInView applies a transform of its own and would otherwise walk straight
        past MIN_ZOOM on a widely spread canvas.
        """
        self.grow_scene_rect()  # fitInView cannot scroll outside the scene rect
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        with self._anchored_to_center():  # keep rect centred while correcting the zoom
            self._scale_to(self.transform().m11())
        self.grow_scene_rect()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grow_scene_rect()

    def showEvent(self, event):
        super().showEvent(event)
        self.grow_scene_rect()

    def _starts_pan(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            return True
        return bool(
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )

    def mousePressEvent(self, event):
        """Override mouse press to implement middle-drag and shift+drag panning"""
        if self._pan_button is None and self._starts_pan(event):
            # Start panning mode
            self._pan_button = event.button()
            self._last_mouse_pos = event.pos()
            # An override beats the per-item cursors set by DraggableCardItem,
            # which would otherwise show a grab hand while panning over a card.
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            # Default behavior (selection)
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse movement for panning or default behavior"""
        self._pointer_pos = event.pos()
        if self._pan_button is not None and self._last_mouse_pos:
            # Calculate how much to pan
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()

            # Make room ahead of the camera before consuming the scrollbar range
            self.grow_scene_rect()

            # Pan the view
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for ending panning or default behavior
        """
        if event.button() == self._pan_button:
            self._pan_button = None
            self._last_mouse_pos = None
            QApplication.restoreOverrideCursor()
            event.accept()
        elif self._pan_button is not None:
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Handle zooming with mouse wheel, anchored under the pointer"""
        zoom_factor = 1.15

        if event.angleDelta().y() > 0:
            self.zoom_by(zoom_factor)
        else:
            self.zoom_by(1.0 / zoom_factor)
