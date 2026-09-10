"""Time base and transform composition for canvas card motion."""

import hashlib
import math
import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QTransform, qAlpha

# ~60 Hz
TICK_MS = 16
MAX_DT = 0.1

EXTRA_PERSPECTIVE_PER_DEGREE = 0.000017

DRIFT_BASE_HZ = 0.05
DRIFT_RATIO = 2.17
DRIFT_OCTAVES = 4
# Sum of the 1/f weights
DRIFT_WEIGHT_SUM = sum(0.5**k for k in range(DRIFT_OCTAVES))

TILT_AMPLITUDE_DEG = 3.0
DRIFT_AMPLITUDE_PX = 1.5

AMBIENT_GAIN_FLOOR = 1e-3

# epsilons to determine when we should redraw
MOTION_EPSILON_PX = 0.25
SHADOW_EPSILON_PX = 1.0
SHADOW_LIFT_EPSILON = 1e-3

# reactive params
REACTIVE_RATE = 12.0
SPIN_RATE = 9.0
ORIENT_RATE = 8.0
LEAN_RATE = 12.0

# How far the card face turns to follow the cursor
# already unmistakable.
HOVER_TILT_DEG = 6.0

LEAN_DEG_PER_PX = 0.16
LEAN_MAX_DEG = 10.0
LEAN_REST_PX = 1e-3

LIFT_REST = 1.0
LIFT_SELECTED = 1.02
LIFT_PRESSED = 1.02
LIFT_HOVER = 1.04
LIFT_DRAG = 1.06
LIFT_PLACED = 1.15

AMBIENT_SCALE_HOVER = 0.2
AMBIENT_SCALE_DRAG = 0.0

# Reactive params
REACTIVE_REST_EPSILON = 1e-4
REACTIVE_REST_VELOCITY = 1e-3

# Lift params
LIFT_STIFFNESS = 260.0
LIFT_DAMPING = 22.0
SPRING_MAX_STEP = 1.0 / 240.0

# shadow params
SHADOW_Z_OFFSET = -0.5
SHADOW_DOWNSAMPLE = 8
SHADOW_BLUR_PASSES = 3
SHADOW_BLUR_RADIUS = 1

SHADOW_BLUR_PX = float(SHADOW_BLUR_RADIUS * SHADOW_BLUR_PASSES * SHADOW_DOWNSAMPLE) # how big the penumbra is
SHADOW_OPACITY = 0.5
SHADOW_REST_OFFSET_PX = 4.0  # how far the shadow sits below a resting card
SHADOW_LIFT_OFFSET_PX = 90.0
SHADOW_LIFT_SPREAD = 0.6


def approach(current, target, rate, dt):
    """step an object toward a specific target by rate"""
    if rate <= 0.0 or dt <= 0.0:
        return current

    return current + (target - current) * (1.0 - math.exp(-rate * dt))


def max_corner_delta(previous, current):
    """The furthest any one corner moved between two sequences of mapped points."""
    worst = 0.0
    for before, after in zip(previous, current, strict=True):
        dx = after.x() - before.x()
        dy = after.y() - before.y()
        distance = math.hypot(dx, dy)
        if distance > worst:
            worst = distance
    return worst


@dataclass
class MotionChannels:
    # Logical rotation in degrees
    orient: float = 0.0

    # ----- ambient --------

    # Perspective tilt in degrees
    tilt_x: float = 0.0
    tilt_y: float = 0.0

    # Visual-only position offset in pixels
    drift_x: float = 0.0
    drift_y: float = 0.0

    # ----- reactive --------

    # Perspective tilt in degrees
    face_x: float = 0.0
    face_y: float = 0.0

    # Z rotation in degrees
    spin: float = 0.0

    # displayed rotation that trails orient in degrees
    orient_lag: float = 0.0

    lift: float = 1.0

    def compose(self, width, height):
        """Fold every channel into one transform about the card's center."""
        cx, cy = width / 2.0, height / 2.0
        tilt_x = self.tilt_x + self.face_x
        tilt_y = self.tilt_y + self.face_y
        spin = self.orient + self.orient_lag + self.spin
        t = QTransform()
        t.translate(cx + self.drift_x, cy + self.drift_y)
        if tilt_x or tilt_y:
            t.setMatrix(
                t.m11(),
                t.m12(),
                -EXTRA_PERSPECTIVE_PER_DEGREE * tilt_y,
                t.m21(),
                t.m22(),
                -EXTRA_PERSPECTIVE_PER_DEGREE * tilt_x,
                t.m31(),
                t.m32(),
                t.m33(),
            )
            t.rotate(tilt_y, Qt.Axis.YAxis)
            t.rotate(tilt_x, Qt.Axis.XAxis)
        if spin:
            t.rotate(spin)
        if self.lift != 1.0:
            t.scale(self.lift, self.lift)
        t.translate(-cx, -cy)
        return t

    def at_rest(self):
        """Whether every motion channel has landed (besides orient)"""
        return (
            self.tilt_x == 0.0
            and self.tilt_y == 0.0
            and self.drift_x == 0.0
            and self.drift_y == 0.0
            and self.face_x == 0.0
            and self.face_y == 0.0
            and self.spin == 0.0
            and self.orient_lag == 0.0
            and self.lift == LIFT_REST
        )

    def corners(self, width, height):
        """The card's four corners in item coordinates."""
        return (
            QPointF(0.0, 0.0),
            QPointF(width, 0.0),
            QPointF(width, height),
            QPointF(0.0, height),
        )

    def snapshot(self):
        return (
            self.orient,
            self.tilt_x,
            self.tilt_y,
            self.drift_x,
            self.drift_y,
            self.face_x,
            self.face_y,
            self.spin,
            self.orient_lag,
            self.lift,
        )


class Spring:
    """Damped harmonic oscillator"""

    __slots__ = ("value", "velocity", "stiffness", "damping")

    def __init__(self, value=1.0, stiffness=LIFT_STIFFNESS, damping=LIFT_DAMPING):
        self.value = value
        self.velocity = 0.0
        self.stiffness = stiffness
        self.damping = damping

    def snap(self, value, velocity=0.0):
        self.value = value
        self.velocity = velocity

    def advance(self, target, dt):
        if dt <= 0.0:
            return self.value
        steps = max(1, math.ceil(dt / SPRING_MAX_STEP))
        h = dt / steps
        for _ in range(steps):
            acceleration = -self.stiffness * (self.value - target) - self.damping * self.velocity
            self.velocity += acceleration * h
            self.value += self.velocity * h
        if (
            abs(self.value - target) < REACTIVE_REST_EPSILON
            and abs(self.velocity) < REACTIVE_REST_VELOCITY
        ):
            self.snap(target)
        return self.value


def rest(value, target, epsilon=REACTIVE_REST_EPSILON):
    """Snap a converging channel onto its target once the difference stops mattering."""
    return target if abs(value - target) < epsilon else value


def _box_blur(alpha, width, height, radius):
    if radius < 1:
        return alpha
    for horizontal in (True, False):
        source = alpha
        alpha = [0] * (width * height)
        outer, inner = (height, width) if horizontal else (width, height)
        stride = 1 if horizontal else width
        base_step = width if horizontal else 1
        for o in range(outer):
            base = o * base_step
            window = sum(source[base + j * stride] for j in range(min(radius + 1, inner)))
            count = min(radius + 1, inner)
            for i in range(inner):
                alpha[base + i * stride] = window // count
                entering = i + radius + 1
                leaving = i - radius
                if entering < inner:
                    window += source[base + entering * stride]
                    count += 1
                if leaving >= 0:
                    window -= source[base + leaving * stride]
                    count -= 1
    return alpha


def build_contact_shadow(pixmap):
    pad = int(round(SHADOW_BLUR_PX))
    width = pixmap.width() + 2 * pad
    height = pixmap.height() + 2 * pad
    if width <= 0 or height <= 0:
        return QPixmap()

    silhouette = QImage(width, height, QImage.Format.Format_ARGB32)
    silhouette.fill(0)
    painter = QPainter(silhouette)
    painter.drawPixmap(pad, pad, pixmap)
    painter.end()

    small_w = max(1, width // SHADOW_DOWNSAMPLE)
    small_h = max(1, height // SHADOW_DOWNSAMPLE)
    small = silhouette.scaled(
        small_w,
        small_h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    alpha = [qAlpha(small.pixel(x, y)) for y in range(small_h) for x in range(small_w)]

    for _ in range(SHADOW_BLUR_PASSES):
        alpha = _box_blur(alpha, small_w, small_h, SHADOW_BLUR_RADIUS)

    blurred = QImage(small_w, small_h, QImage.Format.Format_ARGB32)
    blurred.fill(0)
    for y in range(small_h):
        row = y * small_w
        for x in range(small_w):
            blurred.setPixelColor(x, y, QColor(0, 0, 0, alpha[row + x]))

    return QPixmap.fromImage(
        blurred.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def shadow_geometry(lift):
    """(offset_px, scale, opacity) for shadow under a card at a specific lift value."""
    height = max(0.0, lift - LIFT_REST)
    offset = SHADOW_REST_OFFSET_PX + height * SHADOW_LIFT_OFFSET_PX
    scale = 1.0 + height * SHADOW_LIFT_SPREAD

    # Further away is softer and fainter, but never so faint it stops grounding the card.
    opacity = SHADOW_OPACITY * (1.0 - min(0.45, height * 3.0))
    return offset, scale, opacity


def drift_phases(seed, count):
    """phases in [0, 2*pi)"""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    phases = []

    for i in range(count):
        offset = (i * 2) % len(digest)
        word = int.from_bytes(digest[offset : offset + 2], "big")
        phases.append(word / 65536.0 * math.tau)

    return phases


class PinkOscillator:
    """A 1/f-weighted sum of sines bounded by [-1, 1] + continuous in every derivative."""

    __slots__ = ("_phases",)

    def __init__(self, phases):
        self._phases = phases

    def value(self, t):
        total = 0.0

        for k, phase in enumerate(self._phases):
            frequency = DRIFT_BASE_HZ * DRIFT_RATIO**k
            total += 0.5**k * math.sin(math.tau * frequency * t + phase)

        return total / DRIFT_WEIGHT_SUM


class AmbientDrift:
    __slots__ = ("_oscillators",)

    def __init__(self, seed_text):
        phases = drift_phases(str(seed_text), 4 * DRIFT_OCTAVES)
        self._oscillators = [
            PinkOscillator(phases[i * DRIFT_OCTAVES : (i + 1) * DRIFT_OCTAVES]) for i in range(4)
        ]

    def sample(self, t):
        """both in in degrees and pixels."""
        tilt_x, tilt_y, drift_x, drift_y = (o.value(t) for o in self._oscillators)
        return (
            tilt_x * TILT_AMPLITUDE_DEG,
            tilt_y * TILT_AMPLITUDE_DEG,
            drift_x * DRIFT_AMPLITUDE_PX,
            drift_y * DRIFT_AMPLITUDE_PX,
        )


class MotionClock(QObject):
    tick = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._emit_tick)
        self._subscribers = []
        self._origin = None
        self._last = None

    def subscribe(self, callback):
        """Register a `(t, dt)` callable, starting the clock if it was idle."""
        if callback in self._subscribers:
            return

        self._subscribers.append(callback)
        self.tick.connect(callback)
        if not self._timer.isActive():
            self._origin = time.perf_counter()
            self._last = self._origin
            self._timer.start()

    def unsubscribe(self, callback):
        """Drop a callable, stopping the clock once nothing is left to drive."""
        if callback not in self._subscribers:
            return

        self._subscribers.remove(callback)
        self.tick.disconnect(callback)
        if not self._subscribers:
            self._timer.stop()

    def is_running(self):
        return self._timer.isActive()

    def _emit_tick(self):
        now = time.perf_counter()
        dt = min(now - self._last, MAX_DT)
        self._last = now
        self.tick.emit(now - self._origin, dt)


def system_animations_enabled():
    # let's ask d-bus for some reason
    try:
        from PyQt6.QtDBus import QDBusConnection, QDBusInterface
    except ImportError:  # PyQt6.QtDBus is not guaranteed to be present
        return True

    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return True
        portal = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            bus,
        )
        if not portal.isValid():
            return True

        reply = portal.call("Read", "org.gnome.desktop.interface", "enable-animations")
        if reply.errorName():
            return True

        arguments = reply.arguments()
        if not arguments:
            return True
        value = arguments[0]
        while hasattr(value, "variant"):  # the portal double-wraps in a variant
            value = value.variant()
        if isinstance(value, bool):
            return value
        return True

    except Exception:
        return True
