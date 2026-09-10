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

# Reactive channels converge asymptotically just as the ambient gain does, so they need
# the same floor for the same reason: without one a card that has finished settling holds a
# ten-thousandth of a degree forever, `snapshot()` never repeats, and every card on an idle
# canvas repaints sixty times a second to express nothing. With it, a card at rest composes
# to *exactly* the identity transform.
REACTIVE_REST_EPSILON = 1e-4
REACTIVE_REST_VELOCITY = 1e-3

# The lift spring. omega = sqrt(260) = 16.1 rad/s, so critical damping would be 32.2;
# at 22 the ratio is about 0.68, which overshoots once by a few percent and is done inside
# 300 ms. approach() is first-order and cannot overshoot at all, which is why lift alone
# gets a spring: the settle is the whole point of the gesture.
LIFT_STIFFNESS = 260.0
LIFT_DAMPING = 22.0
# The spring is integrated explicitly, so it is substepped rather than trusted with a dt
# that MAX_DT allows to reach 100 ms.
SPRING_MAX_STEP = 1.0 / 240.0

# The contact shadow. Penumbra separation is what sells "floating", and it needs no ambient
# motion at all to do it.
# A card's shadow sits immediately beneath *that card* rather than beneath every card, so a
# card stacked on another casts onto it — which is what a shadow is for. Half a z-unit down,
# because the canvas allocates whole numbers to cards (see CanvasTab's stacking order) and
# nothing may ever land between a card and its own shadow.
#
# Balatro does the opposite, two-passing each CardArea as {'shadow', 'card'} and suppressing
# shadows outright for the deck and discard piles. That is an accommodation for a *fan* —
# eight cards overlapping by 70%, where interleaving would band a shadow across every one of
# them. A tarot spread is laid out with gaps and stacked only deliberately, so it wants the
# Material Design reading instead: a surface casts onto whatever is below it.
SHADOW_Z_OFFSET = -0.5
SHADOW_DOWNSAMPLE = 8  # the blur is computed at 1/8 scale and scaled back up
SHADOW_BLUR_PASSES = 3  # three box blurs approximate a gaussian closely enough
SHADOW_BLUR_RADIUS = 1  # per pass, in downsampled pixels
# How far the penumbra reaches, in card pixels: three passes of a radius-1 box at 1/8 scale
# put its outermost non-zero sample exactly here. Derived rather than chosen, because the
# silhouette is padded by this much and a pad smaller than the kernel clips the penumbra
# into a hard edge — which is the one thing a contact shadow must not have.
SHADOW_BLUR_PX = float(SHADOW_BLUR_RADIUS * SHADOW_BLUR_PASSES * SHADOW_DOWNSAMPLE)
SHADOW_OPACITY = 0.5
SHADOW_REST_OFFSET_PX = 4.0  # how far the shadow sits below a resting card
SHADOW_LIFT_OFFSET_PX = 90.0  # additional offset per unit of lift above rest
SHADOW_LIFT_SPREAD = 0.6  # how much of the lift the shadow itself takes as scale


def approach(current, target, rate, dt):
    """Move `current` toward `target` by `rate`, independently of framerate.

    The exponential form matters. The obvious `current + (target - current) * rate * dt`
    (and Balatro-Feel's `Lerp(a, b, speed * dt)`) converges at a different speed on a
    144 Hz display than on a 60 Hz one, because repeated linear steps do not compose.
    Repeated exponential steps do: `1 - exp(-rate*t)` splits exactly across any number of
    substeps, so a drag feels the same on every machine. Cheap now, tedious to retrofit.
    """
    if rate <= 0.0 or dt <= 0.0:
        return current
    return current + (target - current) * (1.0 - math.exp(-rate * dt))


def max_corner_delta(previous, current):
    """The furthest any one corner moved between two sequences of mapped points.

    The honest measure of "did this card visibly change": the composed transform mixes
    rotation, scale, drift and a projective term, and no single channel's magnitude
    predicts how far the pixels actually travelled. Four corners do, because every
    transform here is a projectivity and a projectivity's maximum displacement over a
    convex quad is attained at a vertex.
    """
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
    """The named channels that compose into one card's transform.

    Each is owned by exactly one tier of motion, which is what makes the reduced-motion
    setting a single gate rather than a per-effect audit: ambient owns tilt and drift,
    reactive owns spin and lift, and `orient` is not motion at all but card state.
    """

    # Logical rotation in degrees: the reversed-180 state and the rotate-90 command.
    # Card state rather than motion — it survives every gate.
    orient: float = 0.0
    # Perspective tilt in degrees, ambient tier. Rotating the card *plane* rather than
    # spinning the bitmap about the screen normal, which is the artifact channel.
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    # Visual-only position offset in pixels, ambient tier. Never touches pos(), so
    # alignment, snapping and undo keep operating on the logical position.
    drift_x: float = 0.0
    drift_y: float = 0.0
    # Perspective tilt in degrees, reactive tier: the face turning toward the cursor, and
    # the bank angle of a drag. Summed with the ambient tilt rather than sharing it, so
    # that `advance_motion` can scale one tier by the ambient gain without touching this
    # one — which is the whole reason RFC-024 keeps the tiers on separate channels.
    face_x: float = 0.0
    face_y: float = 0.0
    # Z rotation in degrees, reactive tier: a brief response to the user's own action.
    spin: float = 0.0
    # How far the *displayed* rotation still trails `orient`, in degrees, reactive tier.
    # `set_orient` writes the logical angle at once and parks the difference here, so the
    # card sweeps into its new orientation instead of teleporting while every caller that
    # asks for `orient` still reads the exact value it set.
    orient_lag: float = 0.0
    # Uniform scale, reactive tier.
    lift: float = 1.0

    def compose(self, width, height):
        """Fold every channel into one transform, about the card's centre."""
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
        """Whether every motion channel has landed and only `orient` is left.

        The dead-band below has to be bypassed for exactly this state, or it becomes the
        defect `AMBIENT_GAIN_FLOOR` exists to prevent: the last step onto zero is by
        construction the *smallest* one, so a threshold that skipped it would leave a
        faded-out or settled card holding a permanent sliver of tilt. Asking the channels
        rather than tracking a flag means every path that converges — the gain floor,
        `rest()`, `Spring.snap`, `settle_motion` — gets the bypass without knowing about it.
        """
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
        """The card's four corners, in item coordinates."""
        return (
            QPointF(0.0, 0.0),
            QPointF(width, 0.0),
            QPointF(width, height),
            QPointF(0.0, height),
        )

    def snapshot(self):
        """The channel values, for deciding whether a card needs a new transform."""
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
    """A damped harmonic oscillator, for the one channel that has to overshoot.

    `approach()` is first-order: it converges from one side and never passes its target,
    which is right for a tilt chasing the cursor and wrong for a card settling onto the
    table. A settle that does not overshoot reads as the card being lowered by machinery;
    one that overshoots once reads as weight.

    Integrated semi-implicitly and substepped, because an explicit spring is only stable
    while `stiffness * dt^2` stays small and `MAX_DT` permits a 100 ms tick after a modal
    dialog or a suspend. Substepping makes the result framerate-independent as well.
    """

    __slots__ = ("value", "velocity", "stiffness", "damping")

    def __init__(self, value=1.0, stiffness=LIFT_STIFFNESS, damping=LIFT_DAMPING):
        self.value = value
        self.velocity = 0.0
        self.stiffness = stiffness
        self.damping = damping

    def snap(self, value, velocity=0.0):
        """Place the spring, discarding whatever it was doing. Used to launch a settle."""
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
    """One separable box blur over a flat alpha grid, as a sliding window.

    Linear in the number of samples rather than in `samples * radius`: the window is
    advanced by adding one sample and dropping another. That matters because this runs on
    the UI thread when a card is dealt, and a quadratic version of it is the difference
    between the shadow being free and being a visible hitch.
    """
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
    """Bake a soft black silhouette of `pixmap`, once, with `SHADOW_BLUR_PX` of penumbra.

    Deliberately not `QGraphicsDropShadowEffect`, which re-blurs on every paint and would
    put a gaussian in the frame budget of every card on the canvas. The blur is computed on
    an eighth-scale copy — about 2400 samples for a 300x500 card rather than 150,000, which
    is the difference between a Python loop being free and being impossible — and scaled
    back up smoothly. Downsampling before a blur is close to exact: the small image has
    already lost the frequencies the blur was going to remove.

    The result is padded by the blur radius on every side so the penumbra is not clipped,
    and `shadow_offset()` accounts for that padding.
    """
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
    """`(offset_px, scale, opacity)` for a shadow under a card at this `lift`.

    Height is encoded in the *separation* between card and shadow, not in the shadow's
    darkness alone: a card pressed into the felt has a tight, dark contact shadow and a
    lifted one has a wide, faint, displaced one. That relationship is the whole of what
    makes the card read as floating rather than as merely scaled.
    """
    height = max(0.0, lift - LIFT_REST)
    offset = SHADOW_REST_OFFSET_PX + height * SHADOW_LIFT_OFFSET_PX
    scale = 1.0 + height * SHADOW_LIFT_SPREAD
    # Further away is softer and fainter, but never so faint it stops grounding the card.
    opacity = SHADOW_OPACITY * (1.0 - min(0.45, height * 3.0))
    return offset, scale, opacity


def drift_phases(seed_text, count):
    """`count` phases in [0, 2*pi), determined entirely by `seed_text`.

    Deterministic on purpose. `id(item)` is an address and `hash()` is salted per process,
    so either would give a card a different personality every launch; a card should breathe
    the same way each time it is drawn. SHA-256 gives 32 bytes, read two at a time.
    """
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    phases = []
    for i in range(count):
        offset = (i * 2) % len(digest)
        word = int.from_bytes(digest[offset : offset + 2], "big")
        phases.append(word / 65536.0 * math.tau)
    return phases


class PinkOscillator:
    """A 1/f-weighted sum of sines, bounded by +/-1 and continuous in every derivative.

    A pure sine reads mechanical and white noise reads nervous; 1/f reads alive. Being
    C-infinity also means there are no joints for the motion to stall at, which is exactly
    the defect the old three-segment wobble had — it cannot recur here by construction.
    """

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
    """One card's share of the ambient tier: how it tilts and wanders when left alone.

    Four independent oscillators rather than one waveform shared between axes — sharing
    would make the card sweep back and forth along a straight line instead of precessing.
    """

    __slots__ = ("_oscillators",)

    def __init__(self, seed_text):
        phases = drift_phases(str(seed_text), 4 * DRIFT_OCTAVES)
        self._oscillators = [
            PinkOscillator(phases[i * DRIFT_OCTAVES : (i + 1) * DRIFT_OCTAVES]) for i in range(4)
        ]

    def sample(self, t):
        """`(tilt_x, tilt_y, drift_x, drift_y)` at time `t`, already in degrees and pixels."""
        tilt_x, tilt_y, drift_x, drift_y = (o.value(t) for o in self._oscillators)
        return (
            tilt_x * TILT_AMPLITUDE_DEG,
            tilt_y * TILT_AMPLITUDE_DEG,
            drift_x * DRIFT_AMPLITUDE_PX,
            drift_y * DRIFT_AMPLITUDE_PX,
        )


class MotionClock(QObject):
    """One timebase per canvas tab, running only while something listens.

    Subscribers are callables taking `(t, dt)` in seconds — `t` monotonic since the clock
    was created, `dt` since the previous tick and clamped to `MAX_DT`. The clock keeps no
    reference to any card: a subscriber walks its own scene, so an item destroyed on the
    C++ side simply stops being visited, and there is no dangling pointer to guard against.
    """

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
    """Whether the desktop wants animations, via the XDG settings portal.

    Qt 6.10 surfaces no reduced-motion hint of its own, and inside the Flatpak sandbox the
    portal is the only way to see the host's preference. Every failure path returns True:
    a desktop-integration problem must never be what disables the app's own feature.
    """
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
    except Exception:  # a portal read is never worth propagating into the UI
        return True
