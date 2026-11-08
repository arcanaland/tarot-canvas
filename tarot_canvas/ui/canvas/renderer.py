"""Whether the window and its canvases paint through GL or QPainter's raster engine."""

import logging
import os
import sys
from functools import cache

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QGuiApplication

from tarot_canvas.settings import (
    HARDWARE_ACCELERATION_DEFAULT,
    HARDWARE_ACCELERATION_KEY,
    get_settings,
)
from tarot_canvas.ui.canvas.gl_marker import GlMarker, current_key, marker_path

RENDERER_ENV = "TAROT_CANVAS_RENDERER"
FORCED_VALUES = ("raster", "gl")
HEADLESS_PLATFORMS = ("offscreen", "minimal")
# Software GL is slower than raster for the canvas
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swrast", "software rasterizer")
GL_RENDERER = 0x1F01

log = logging.getLogger("TarotCanvas.canvas")


def choose(platform, system, forced, enabled, failed, probe):
    """(GL or not, the rule that decided). failed() and probe() are called only when reached;
    probe() returns the GL_RENDERER string, or None without a working context."""
    if forced == "raster":
        return False, "forced"
    if platform in HEADLESS_PLATFORMS:
        return False, "headless"
    if forced == "gl":
        return True, "forced"
    if system != "linux":
        return False, "not linux"
    if not enabled:
        return False, "preference off"
    if failed():
        return False, "failed before"
    renderer = probe()
    if renderer is None:
        return False, "no context"
    if any(name in renderer.lower() for name in SOFTWARE_RENDERERS):
        return False, "software"
    return True, "hardware"


def gl_renderer():
    """GL_RENDERER from a throwaway context, or None when none can be made current."""
    import ctypes

    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext

    try:
        context = QOpenGLContext()
        if not context.create():
            return None
        surface = QOffscreenSurface()
        surface.setFormat(context.format())
        surface.create()
        try:
            if not context.makeCurrent(surface):
                return None
            address = context.getProcAddress(b"glGetString")
            if not address:
                return None
            get_string = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_uint)(int(address))
            renderer = get_string(GL_RENDERER)
            context.doneCurrent()
            return renderer.decode(errors="replace") if renderer else None
        finally:
            surface.destroy()
    except Exception:
        log.exception("Could not probe the GL renderer")
        return None


_marker = None
_canvas_watched = False
_window_watch = None


def canvas_uses_gl():
    return _choice()[0]


def canvas_renderer_rule():
    """The rule canvas_uses_gl() went by: "hardware", "software", "failed before", …"""
    return _choice()[1]


def forget_renderer_choice():
    """Choose again on the next call, e.g. after the forcing env var changes."""
    _choice.cache_clear()


@cache
def _choice():
    global _marker
    _marker = None
    forced = os.environ.get(RENDERER_ENV, "").strip().lower()
    forced = forced if forced in FORCED_VALUES else None
    enabled = get_settings().value(
        HARDWARE_ACCELERATION_KEY, HARDWARE_ACCELERATION_DEFAULT, type=bool
    )
    seen = []

    def failed():
        global _marker
        _marker = GlMarker(marker_path(), current_key())
        return _marker.failed()

    def probe():
        seen.append(gl_renderer())
        return seen[0]

    uses_gl, rule = choose(
        QGuiApplication.platformName(), sys.platform, forced, bool(enabled), failed, probe
    )
    if _marker is not None and not uses_gl:
        if rule != "failed before":
            _marker.clear()
        _marker = None
    log.info(
        "Renderer: %s (%s; GL_RENDERER: %s)",
        "gl" if uses_gl else "raster",
        rule,
        seen[0] if seen else "not probed",
    )
    return uses_gl, rule


class _FirstExpose(QObject):
    def __init__(self, window, done):
        super().__init__(window)
        self._done = done
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        global _window_watch
        if event.type() == QEvent.Type.Expose and watched.isExposed():
            watched.removeEventFilter(self)
            QTimer.singleShot(0, self._done)
            _window_watch = None
        return False


def watch_window(window):
    """Keeps the marker armed until the turn after the QWindow's first exposure."""
    global _window_watch
    if _marker is None:
        return
    _marker.arm("window")
    # Held here, or PyQt collects the filter and it never runs
    _window_watch = _FirstExpose(window, _marker.clear)


def watch_first_canvas(viewport):
    """Keeps the marker armed until the session's first GL canvas swaps a frame."""
    global _canvas_watched
    if _marker is None or _canvas_watched:
        return
    _canvas_watched = True
    _marker.arm("canvas")
    viewport.frameSwapped.connect(_marker.clear, Qt.ConnectionType.SingleShotConnection)


def gl_failed(stage):
    if _marker is not None:
        _marker.fail(stage)
