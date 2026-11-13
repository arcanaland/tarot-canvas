"""A dreamy swirly background. Inspired by a certain award-winning deck-building roguelike."""

import contextlib
import logging
import math
import sys
import time
from array import array
from importlib.resources import files

from PyQt6.QtCore import QObject, QRect, QSize, QTimer
from PyQt6.QtGui import (
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QSurfaceFormat,
    QVector2D,
    QVector3D,
    QVector4D,
)

from tarot_canvas.ui.canvas.ground import GROUND_HUE_DEFAULT, GROUND_HUES
from tarot_canvas.ui.canvas.motion import TICK_MS
from tarot_canvas.ui.canvas.renderer import canvas_renderer_rule

log = logging.getLogger(__name__)

# Where t sits when the ground is still
STILL_T = 7.0

PARAMS = {
    "twirl": 0.05,
    "spin": 0.144,
    "blooms": 3,
    "bloom": 1.88,
    "bloom_size": 1.08,
    "rounds": 5,
    "warp": 0.648,
    "contrast": 0.648,
    "speed": 0.178,
    "pixel": 4,
    "every": 2,
    "parallax": True,
    "parallax_pan": 0.376,
    "parallax_zoom": 0.08,
}

SHADERS = files("tarot_canvas.resources").joinpath("shaders")

LEGACY_HEADER = ("#version 120\n", "#version 120\n#define OUT_COLOUR gl_FragColor\n")
CORE_HEADER = (
    "#version 330 core\n#define attribute in\n",
    "#version 330 core\nout vec4 frag_colour;\n#define OUT_COLOUR frag_colour\n",
)

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406


MAX_BLOOMS = 8


def _hash(n):
    return (math.sin(n * 91.3458) * 47453.5453) % 1.0


def bloom_data(t, values):
    """Each bloom's center, turn and radius at t. Always MAX_BLOOMS long."""
    blooms = []
    for i in range(MAX_BLOOMS):
        n = i * 7.0
        cx = math.sin(t * (0.07 + 0.05 * _hash(n)) + math.tau * _hash(n + 1)) * 2.4
        cy = math.cos(t * (0.05 + 0.04 * _hash(n + 2)) + math.tau * _hash(n + 3)) * 1.5
        sense = 1.0 if _hash(n + 4) > 0.5 else -1.0
        turn = sense * values["bloom"] * (0.6 + 0.8 * _hash(n + 5))
        size = values["bloom_size"] * (0.6 + 0.8 * _hash(n + 6))
        blooms.append(QVector4D(cx, cy, turn, size))
    return blooms


# The raster governor. Used in case we are falling behind drawing the swirls.
TICKS_PER_S = 1000.0 / TICK_MS
SHARE_MS = 250.0
STILL_MS = 16.7
MAX_STRIDE = 16
# A slower rate is taken at once
RECOVER_S = 2.0
# While held still, how often one render measures whether it can move again
PROBE_S = 5.0
# Weight of the newest paint in the running cost
COST_WEIGHT = 0.25

# Why the canvas paints with raster
NO_FIELD_RULES = ("failed before",)
STILL_RULES = ("preference off",)

# Every render+readback in ms (for benchmarking)
render_log = None


def colour_values(hue):
    """The shader's colour uniforms from a GroundHue"""
    return dict(zip(("colour_1", "colour_2", "colour_3"), hue.swirl, strict=True))


def surface_format():
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setSamples(0)
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    if sys.platform == "darwin":
        # macOS has no compatibility profile past 2.1; never run
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    else:
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    return fmt


class SwirlField:
    """Offscreen GL context rendering our shader into a throwaway framebuffer."""

    def __init__(self):
        self.context = None
        self.surface = None
        self.program = None
        self.fbo = None
        self.buffer = None
        self.vao = None
        self.gl = None
        self.renderer = None
        self.size = QSize()

    def create(self):
        """Raises RuntimeError with the reason when any part cannot be made."""
        from PyQt6.QtOpenGL import (
            QOpenGLBuffer,
            QOpenGLShader,
            QOpenGLShaderProgram,
            QOpenGLVersionFunctionsFactory,
            QOpenGLVersionProfile,
            QOpenGLVertexArrayObject,
        )

        self.context = QOpenGLContext()
        self.context.setFormat(surface_format())
        if not self.context.create():
            raise RuntimeError("no GL context")
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.context.format())
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("no offscreen surface")
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError("context would not make current")
        try:
            fmt = self.context.format()
            core = fmt.profile() == QSurfaceFormat.OpenGLContextProfile.CoreProfile
            profile = QOpenGLVersionProfile()
            profile.setVersion(2, 0)
            self.gl = QOpenGLVersionFunctionsFactory.get(profile, self.context)
            if self.gl is None:
                raise RuntimeError("no OpenGL 2.0 functions")
            self.renderer = self.gl.glGetString(0x1F01)
            vertex_header, fragment_header = CORE_HEADER if core else LEGACY_HEADER

            vertex = SHADERS.joinpath("swirl.vert").read_text(encoding="utf-8")
            fragment = SHADERS.joinpath("swirl.frag").read_text(encoding="utf-8")

            program = QOpenGLShaderProgram()
            if not program.addCacheableShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex, vertex_header + vertex
            ):
                raise RuntimeError(f"vertex shader: {program.log()}")
            if not program.addCacheableShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment, fragment_header + fragment
            ):
                raise RuntimeError(f"fragment shader: {program.log()}")
            program.bindAttributeLocation("corner", 0)
            if not program.link():
                raise RuntimeError(f"link: {program.log()}")
            self.program = program

            # One triangle that covers the whole clip square
            if core:
                self.vao = QOpenGLVertexArrayObject()
                self.vao.create()
                self.vao.bind()

            corners = array("f", (-1.0, -1.0, 3.0, -1.0, -1.0, 3.0))
            self.buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not self.buffer.create():
                raise RuntimeError("no vertex buffer")
            self.buffer.bind()
            self.buffer.allocate(corners.tobytes(), len(corners) * corners.itemsize)
            program.bind()
            program.enableAttributeArray(0)
            program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 0)
            program.release()
            self.buffer.release()
            if self.vao is not None:
                self.vao.release()
            log.info(
                "Swirl field: GL %d.%d %s, GL_RENDERER %s",
                fmt.majorVersion(),
                fmt.minorVersion(),
                "core" if core else "compatibility",
                self.renderer,
            )
        finally:
            self.context.doneCurrent()

    def _ensure_fbo(self, size):
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject

        if self.fbo is not None and self.size == size:
            return
        self.fbo = None
        self.fbo = QOpenGLFramebufferObject(size)
        if not self.fbo.isValid():
            self.fbo = None
            raise RuntimeError(f"no {size.width()}x{size.height()} framebuffer")
        self.size = QSize(size)

    def render(self, t, size, values, centre, scale):
        """The field at time t as a size image, centre in field pixels from the top left."""
        start = time.perf_counter()
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError("context would not make current")
        try:
            self._ensure_fbo(size)
            self.fbo.bind()
            self.gl.glViewport(0, 0, size.width(), size.height())

            program = self.program
            program.bind()
            # what an ergonomic API!
            program.setUniformValue("resolution", QVector2D(size.width(), size.height()))
            program.setUniformValue("centre", QVector2D(*centre))
            program.setUniformValue("scale", float(scale))
            program.setUniformValue("t", float(t))
            program.setUniformValue("twirl", float(values["twirl"]))
            program.setUniformValue("spin", float(values["spin"]))
            program.setUniformValue("blooms", int(values["blooms"]))
            program.setUniformValueArray("bloom_at", bloom_data(t, values))
            program.setUniformValue("rounds", int(values["rounds"]))
            program.setUniformValue("warp", float(values["warp"]))
            program.setUniformValue("contrast", float(values["contrast"]))

            for name in ("colour_1", "colour_2", "colour_3"):
                c = values[name]
                program.setUniformValue(name, QVector3D(c.redF(), c.greenF(), c.blueF()))

            if self.vao is not None:
                self.vao.bind()
            else:
                self.buffer.bind()
                program.enableAttributeArray(0)
                program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 0)

            self.gl.glDrawArrays(GL_TRIANGLES, 0, 3)
            if self.vao is not None:
                self.vao.release()
            else:
                self.buffer.release()

            program.release()
            image = self.fbo.toImage()
            self.fbo.release()
        finally:
            self.context.doneCurrent()

        if render_log is not None:
            render_log.append((time.perf_counter() - start) * 1000.0)

        return image

    def destroy(self):
        if self.context is None:
            return
        if self.surface is not None and self.surface.isValid():
            self.context.makeCurrent(self.surface)
        self.fbo = None
        self.program = None
        if self.buffer is not None:
            self.buffer.destroy()
        if self.vao is not None:
            self.vao.destroy()
        self.buffer = self.vao = None
        self.context.doneCurrent()
        if self.surface is not None:
            self.surface.destroy()
        self.context = self.surface = None


_field = None
_field_failed = False


def field():
    """The process's SwirlField, or None when GL cannot draw one here."""
    global _field, _field_failed
    if _field is not None or _field_failed:
        return _field
    rule = canvas_renderer_rule()
    if rule in NO_FIELD_RULES:
        # The driver crashed a canvas before, and this context is not in the marker
        _field_failed = True
        log.info("The swirl ground draws the gradient: GL %s", rule)
        return None
    from PyQt6.QtWidgets import QApplication

    candidate = SwirlField()
    try:
        candidate.create()
    except Exception as error:
        _field_failed = True
        log.warning("The swirl ground has no GL (%s); drawing the gradient instead", error)
        with contextlib.suppress(Exception):
            candidate.destroy()
        return None
    _field = candidate
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(_destroy_field)
    return _field


def _destroy_field():
    global _field
    if _field is not None:
        _field.destroy()
        _field = None


def field_size(viewport_size, dpr, pixel):
    """ceil(device px / pixel), at least 1x1."""
    return QSize(
        max(1, math.ceil(viewport_size.width() * dpr / pixel)),
        max(1, math.ceil(viewport_size.height() * dpr / pixel)),
    )


def stride_for(cost_ms, base):
    """Ticks per render for a full repaint of cost_ms, or None to hold still."""
    if cost_ms >= STILL_MS:
        return None

    stride = max(base, math.ceil(cost_ms * TICKS_PER_S / SHARE_MS))
    return stride if stride <= MAX_STRIDE else None


class Governor:
    """How often a raster ground renders."""

    def __init__(self, base):
        self.base = base
        self.cost = None
        # Ticks per render, or None while held still
        self.stride = base
        # Seconds the measured rate has wanted to be faster than the current one
        self._faster_for = 0.0
        self._still_for = 0.0

    def measured(self, ms):
        self.cost = ms if self.cost is None else self.cost + COST_WEIGHT * (ms - self.cost)
        wanted = stride_for(self.cost, self.base)
        if _slower(wanted, self.stride):
            self.stride = wanted
            self._faster_for = 0.0

    def tick(self, dt):
        """True when a still ground should render one probe frame."""
        wanted = stride_for(self.cost, self.base) if self.cost is not None else self.base
        if _slower(self.stride, wanted):
            self._faster_for += dt
            if self._faster_for >= RECOVER_S:
                self.stride = wanted
                self._faster_for = 0.0
        else:
            self._faster_for = 0.0
        if self.stride is not None:
            self._still_for = 0.0
            return False
        self._still_for += dt
        if self._still_for >= PROBE_S:
            self._still_for = 0.0
            return True
        return False


def _slower(a, b):
    """Whether stride a renders less often than stride b (None is never)."""
    if a is None:
        return b is not None

    return b is not None and a > b


def _is_gl(viewport):
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget

    return isinstance(viewport, QOpenGLWidget)


class SwirlGround(QObject):
    """One view's swirl: its paused clock, its last image, and when to draw the next."""

    def __init__(self, view, field, parent=None):
        super().__init__(parent)
        self.view = view
        self.field = field
        self.t = STILL_T
        self.ticks = 0
        # The shader's three colours, from the chosen GroundHue
        self.colours = colour_values(GROUND_HUES[GROUND_HUE_DEFAULT])
        self.image = None
        self.animating = False
        # The camera moved since the last render
        self.dirty = False
        # Hardware acceleration is off: the user asked for no GPU work per frame
        self.still = canvas_renderer_rule() in STILL_RULES
        self.governor = Governor(int(PARAMS["every"]))
        # The next paint follows a render, so it repainted everything: time it
        self._measure = False
        self._failed = False
        self._pending = QTimer(self, singleShot=True, interval=0)
        self._pending.timeout.connect(self.render)
        view.camera_moved.connect(self._on_camera_moved)

    def detach(self):
        self._pending.stop()
        self.view.camera_moved.disconnect(self._on_camera_moved)

    def _on_camera_moved(self):
        if PARAMS["parallax"] or self.image is None or self._stale_size():
            self.dirty = True
            # A rendering tick is coming anyway
            if not self.animating:
                self.request()

    def request(self):
        """Render on the next turn of the event loop."""
        if not self._failed:
            self._pending.start()

    def advance(self, dt, allowed, pace=1.0):
        """One MotionClock tick, with the field's time running at pace. On raster the governor
        picks how often to render."""
        allowed = allowed and not self.still
        gl = _is_gl(self.view.viewport())
        stride = int(PARAMS["every"])

        if allowed and not gl:
            probe = self.governor.tick(dt)
            if self.governor.stride is None:
                # Held still: t waits, so a probe redraws the same frame
                allowed = False
                if probe:
                    self.request()
            else:
                stride = self.governor.stride

        if self.animating and not allowed and self.dirty:
            self.request()

        self.animating = allowed
        if not allowed:
            return

        self.t += dt * PARAMS["speed"] * pace
        self.ticks += 1
        if self.ticks % max(1, stride) == 0:
            self.render()

    def painted(self, ms):
        """The viewport's paint took ms. Only one that follows a render repainted everything."""
        if self._measure and not _is_gl(self.view.viewport()):
            self.governor.measured(ms)

        self._measure = False

    def stop(self):
        """The clock no longer ticks this ground: camera moves render on their own."""
        self.animating = False
        if self.dirty:
            self.request()

    def _target_size(self):
        viewport = self.view.viewport()
        return field_size(viewport.size(), viewport.devicePixelRatioF() or 1.0, PARAMS["pixel"])

    def _stale_size(self):
        return self.image is not None and self.image.size() != self._target_size()

    def _centre_and_scale(self):
        """Where the field's centre sits, in field px, and how far it is scaled."""
        view = self.view
        viewport = view.viewport()
        to_field = (viewport.devicePixelRatioF() or 1.0) / PARAMS["pixel"]
        cx, cy = viewport.width() / 2.0, viewport.height() / 2.0
        scale = 1.0
        if PARAMS["parallax"]:
            origin = view.mapFromScene(0.0, 0.0)
            pan = PARAMS["parallax_pan"]
            cx += pan * (origin.x() - cx)
            cy += pan * (origin.y() - cy)
            zoom = abs(view.transform().m11()) or 1.0
            scale = zoom ** PARAMS["parallax_zoom"]
        return (cx * to_field, cy * to_field), scale

    def render(self):
        self._pending.stop()
        if self._failed:
            return
        self.dirty = False
        size = self._target_size()
        centre, scale = self._centre_and_scale()
        try:
            values = {**PARAMS, **self.colours}
            self.image = self.field.render(self.t, size, values, centre, scale)
            self._measure = True
        except Exception as error:
            self._failed = True
            self.image = None
            log.warning("The swirl ground stopped rendering (%s)", error)
        self.view.viewport().update()

    def paint(self, painter, rect):
        """Draw the last image over the viewport. False when there is none."""
        if self.image is None:
            self.request()
            return False
        if self._stale_size():
            self.request()
        painter.save()
        painter.resetTransform()
        # Bilinear: nearest-neighbour blocks read as pixelated
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QRect(0, 0, rect.width(), rect.height()), self.image)
        painter.restore()
        return True
