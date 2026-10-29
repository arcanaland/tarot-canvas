"""Whether the canvas paints through GL or QPainter's raster engine."""

import logging
import os
import sys
from functools import cache

from PyQt6.QtGui import QGuiApplication

RENDERER_ENV = "TAROT_CANVAS_RENDERER"
FORCED_VALUES = ("raster", "gl")
HEADLESS_PLATFORMS = ("offscreen", "minimal")
# Software GL is slower than raster for the canvas
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swrast", "software rasterizer")
GL_RENDERER = 0x1F01

log = logging.getLogger("TarotCanvas.canvas")


def choose(platform, system, forced, probe):
    """True for GL. probe() returns the GL_RENDERER string, or None without a working context."""
    if forced == "raster" or platform in HEADLESS_PLATFORMS:
        return False
    if forced == "gl":
        return True
    if system != "linux":
        return False
    renderer = probe()
    if renderer is None:
        return False
    return not any(name in renderer.lower() for name in SOFTWARE_RENDERERS)


def gl_renderer():
    """GL_RENDERER from a throwaway context, or None when none can be made current."""
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext
    from PyQt6.QtOpenGL import QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile

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
            profile = QOpenGLVersionProfile()
            profile.setVersion(2, 0)
            functions = QOpenGLVersionFunctionsFactory.get(profile, context)
            renderer = functions.glGetString(GL_RENDERER) if functions else None
            context.doneCurrent()
            return renderer
        finally:
            surface.destroy()
    except Exception:
        log.exception("Could not probe the GL renderer")
        return None


@cache
def canvas_uses_gl():
    forced = os.environ.get(RENDERER_ENV, "").strip().lower()
    forced = forced if forced in FORCED_VALUES else None
    seen = []

    def probe():
        seen.append(gl_renderer())
        return seen[0]

    uses_gl = choose(QGuiApplication.platformName(), sys.platform, forced, probe)
    log.info(
        "Canvas renderer: %s (forced: %s, GL_RENDERER: %s)",
        "gl" if uses_gl else "raster",
        forced,
        seen[0] if seen else "not probed",
    )
    return uses_gl
