"""A CanvasTab under benchmark conditions."""

import random
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PyQt6.QtWidgets import QApplication

from bench.env import BenchError
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.detail import load_card_art
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab

SYNTHETIC_ART_SIZE = QSize(720, 1200)
SYNTHETIC_ART_COUNT = 8
ART_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

SETTLE_MS = 1200

LAYOUT_SEED = 1909

DEFAULT_SIZE = QSize(1600, 1000)


def synthetic_art(directory):
    """Write card-sized images to directory and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(SYNTHETIC_ART_COUNT):
        image = QImage(SYNTHETIC_ART_SIZE, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        gradient = QLinearGradient(0, 0, image.width(), image.height())
        gradient.setColorAt(0, QColor.fromHsv(i * 360 // SYNTHETIC_ART_COUNT, 140, 220))
        gradient.setColorAt(1, QColor.fromHsv((i * 47) % 360, 200, 90))
        painter.fillRect(image.rect(), gradient)
        rng = random.Random(i)
        for _ in range(40):
            painter.fillRect(
                QRectF(rng.uniform(0, 680), rng.uniform(0, 1160), rng.uniform(8, 160), 12),
                QColor.fromHsv(rng.randrange(360), 120, 240),
            )
        painter.end()
        path = directory / f"{i:02}.png"
        image.save(str(path))
        paths.append(path)
    return paths


def art_in(directory):
    """Every card image under directory, sorted."""
    paths = sorted(p for p in Path(directory).rglob("*") if p.suffix.lower() in ART_SUFFIXES)
    if not paths:
        raise BenchError(f"no card art under {directory}")
    return paths


class PaintCounter(QObject):
    """Counts paint events reaching the viewport."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 0

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Paint:
            self.count += 1
        return False


def pump(ms):
    """Run the event loop for ms of wall time."""
    app = QApplication.instance()
    deadline = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()


class BenchCanvas:
    """A CanvasTab to bench."""

    def __init__(self, viewport="raster", size=DEFAULT_SIZE, art=()):
        self.viewport_kind = viewport
        self.art = [(*load_card_art(str(path)), str(path)) for path in art]
        self.ambient = False

        tab = CanvasTab()
        if viewport == "gl":
            self._use_gl(tab)
        tab.resize(size)
        tab.show()
        pump(SETTLE_MS)
        # ensure_window_bounds may have capped the window on a small screen
        tab.window().setMaximumSize(QSize(16777215, 16777215))
        tab.resize(size)
        pump(50)

        # The bench is the clock
        tab.motion_clock.unsubscribe(tab._advance_motion)
        tab.desktop_wants_animation = True
        tab.ambient_is_allowed = lambda: self.ambient
        self.tab = tab

        self.paints = PaintCounter(tab)
        tab.view.viewport().installEventFilter(self.paints)
        self.fence = lambda: None
        self.gl_renderer = None
        if viewport == "gl":
            self._attach_gl()

    @staticmethod
    def _use_gl(tab):
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
        from PyQt6.QtWidgets import QGraphicsView

        platform = QApplication.platformName()
        if platform == "offscreen":
            raise BenchError(
                "the offscreen platform cannot show a QOpenGLWidget; "
                "run under a compositor, e.g. `just bench headless`"
            )
        tab.view.setViewport(QOpenGLWidget())
        tab.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def _attach_gl(self):
        """Resolve the viewport's GL entry points; they must be looked up while current."""
        from PyQt6.QtOpenGL import QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile

        widget = self.tab.view.viewport()
        context = widget.context()
        if not widget.isValid() or context is None:
            raise BenchError("the GL viewport has no context; GL is not working here")
        profile = QOpenGLVersionProfile()
        profile.setVersion(2, 0)
        widget.makeCurrent()
        try:
            functions = QOpenGLVersionFunctionsFactory.get(profile, context)
            if functions is None:
                raise BenchError("no OpenGL 2.0 functions for the viewport's context")
            self.gl_renderer = functions.glGetString(0x1F01)  # GL_RENDERER
        finally:
            widget.doneCurrent()

        def fence():
            """Block until the GPU has drawn the viewport, so paint time includes it."""
            widget.makeCurrent()
            functions.glFinish()
            widget.doneCurrent()

        self.fence = fence
        self._gl = (widget, functions)

    def cards(self):
        """Cards bottom to top."""
        return sorted(self.tab.cards(), key=lambda card: card.zValue())

    def populate(self, count):
        """Replace the canvas's cards with count cards scattered over the viewport."""
        tab = self.tab
        for card in tab.cards():
            tab.scene.removeItem(card)
        tab.view.reset_zoom()

        visible = tab.view.mapToScene(tab.view.viewport().rect()).boundingRect()
        rng = random.Random(LAYOUT_SEED)
        for i in range(count):
            pixmap, source_size, path = self.art[i % len(self.art)]
            # A copy per card, as though each were different art
            card = DraggableCardItem(pixmap.copy(), {"id": f"bench-{i}"}, tab)
            card.set_art_source(path, source_size)
            card.setZValue(tab.take_top_z())
            card.setPos(
                rng.uniform(visible.left(), max(visible.left(), visible.right() - pixmap.width())),
                rng.uniform(visible.top(), max(visible.top(), visible.bottom() - pixmap.height())),
            )
            tab.scene.addItem(card)

        tab.view.centerOn(visible.center())
        tab.settle_motion()
        tab.view.grow_scene_rect()
        pump(50)

    def scroll_to(self, point):
        self.tab.view.grow_scene_rect()
        self.tab.view.horizontalScrollBar().setValue(round(point.x()))
        self.tab.view.verticalScrollBar().setValue(round(point.y()))

    def scroll_position(self):
        view = self.tab.view
        return QPointF(view.horizontalScrollBar().value(), view.verticalScrollBar().value())

    def repaint_all(self):
        self.tab.view.viewport().update()

    def snapshot(self, path):
        """Save what the viewport shows, GL included."""
        viewport = self.tab.view.viewport()
        image = self._read_gl() if self.gl_renderer else viewport.grab().toImage()
        image.save(str(path))

    def _read_gl(self):
        """The viewport's framebuffer as last painted."""
        from PyQt6.QtGui import QImage

        widget, functions = self._gl
        ratio = widget.devicePixelRatioF()
        width, height = round(widget.width() * ratio), round(widget.height() * ratio)
        widget.makeCurrent()
        try:
            # PyQt only wraps GL_FLOAT readback, as a tuple; slow, but this is a snapshot
            pixels = functions.glReadPixels(0, 0, width, height, 0x1908, 0x1406)  # RGBA, FLOAT
        finally:
            widget.doneCurrent()
        data = bytes(round(min(max(v, 0.0), 1.0) * 255) for v in pixels)
        image = QImage(data, width, height, QImage.Format.Format_RGBA8888)
        return image.mirrored(False, True)

    def close(self):
        self.tab.close()
        self.tab.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    @property
    def device_pixel_ratio(self):
        return self.tab.view.viewport().devicePixelRatioF()

    @property
    def viewport_size(self):
        size = self.tab.view.viewport().size()
        return [size.width(), size.height()]
