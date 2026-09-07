"""Time base and transform composition for canvas card motion.

This is the substrate the canvas's motion is built on. A card with every channel at rest
composes to the identity transform and sits exactly where it is put; motion arrives by
writing channels, and the ambient tier at the bottom of this file is the first thing to do
so — a slow 1/f drift of the card *plane*, never a spin about the screen normal.

Two rules shape everything here:

* **One transform, composed.** Nothing calls `setRotation`, `setScale` or
  `setTransformOriginPoint` on a card. Every frame folds the named channels into a single
  `QTransform` and calls `setTransform` once. The card's rotation therefore has exactly one
  claimant, which is what the previous wobble implementation could not manage.
* **One clock.** A single `QTimer` per canvas tab drives every card, rather than each card
  owning a randomised timeline. That collapses the uncorrelated repaints, and it gives one
  place to switch everything off when the tab is hidden.
"""

import hashlib
import math
import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QTransform

# ~60 Hz. Deliberately not vsync-locked: QGraphicsView gives us no frame callback, and the
# resulting 16-vs-16.67 ms beat is a far smaller artifact than the ones it replaces.
TICK_MS = 16

# An event loop that stalls (a modal dialog, a suspend) must not hand the next tick a dt
# that teleports every card. Cap it and let the motion resume from where it was.
MAX_DT = 0.1

# Extra projective strength per degree of tilt, on top of the divide Qt's own
# `rotate(angle, axis)` already applies at an effective viewing distance of 1024 px.
# Matching that with a second equal term puts the camera at roughly 512 px, which on a
# 300x500 card tapers the two vertical edges about 3% at 3 degrees — enough to read as a
# plane turning in space, with no perceptible change in the card's size.
#
# **The sign matters and is applied at the use site, not stored here.** In this
# composition order Qt's own term is negative; the substrate shipped a positive
# 0.00015, which does not merely overshoot — it *subtracts* from Qt's divide and, at that
# magnitude, inverts the perspective, so the edge rotating away from the viewer grows
# instead of shrinking. Measured on a 300x500 card at 3 degrees it tapered the edges 12%
# the wrong way and shrank the width 6.7%, which at ambient frequencies reads as the card
# pumping in size rather than tilting.
#
# Proportional rather than constant so the transform is exactly affine at zero tilt: a
# constant term would need an `if tilt` guard, putting a discontinuity precisely where
# drift spends most of its time — crossing zero.
EXTRA_PERSPECTIVE_PER_DEGREE = 0.000017

# The ambient drift generator. Four sines an incommensurate ratio apart, weighted 1/f, so
# the sum never repeats on any timescale a user will sit through and reads as *alive*
# rather than mechanical: candle flame, breath and wind are all 1/f. The base period is
# 20 seconds; the fastest octave is still under 0.5 Hz.
DRIFT_BASE_HZ = 0.05
DRIFT_RATIO = 2.17
DRIFT_OCTAVES = 4
# Sum of the 1/f weights, so an oscillator's output is bounded by exactly +/-1.
DRIFT_WEIGHT_SUM = sum(0.5**k for k in range(DRIFT_OCTAVES))

# Roughly Balatro divided by eight. Its autoTiltAmount of 30 degrees is for a card held at
# arm's length in a loud roguelike; a tarot spread is laid flat and read slowly. The
# failure mode here is an amplitude failure, not a technique failure — if in doubt, halve
# both of these.
TILT_AMPLITUDE_DEG = 3.0
DRIFT_AMPLITUDE_PX = 1.5

# Below this, a fading ambient gain is treated as off. approach() is asymptotic, so
# without a floor a faded-out canvas keeps a permanent sliver of tilt and repaints for it.
AMBIENT_GAIN_FLOOR = 1e-3


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
    # Z rotation in degrees, reactive tier: a brief response to the user's own action.
    spin: float = 0.0
    # Uniform scale, reactive tier.
    lift: float = 1.0

    def compose(self, width, height):
        """Fold every channel into one transform, about the card's centre."""
        cx, cy = width / 2.0, height / 2.0
        t = QTransform()
        t.translate(cx + self.drift_x, cy + self.drift_y)
        if self.tilt_x or self.tilt_y:
            t.setMatrix(
                t.m11(),
                t.m12(),
                -EXTRA_PERSPECTIVE_PER_DEGREE * self.tilt_y,
                t.m21(),
                t.m22(),
                -EXTRA_PERSPECTIVE_PER_DEGREE * self.tilt_x,
                t.m31(),
                t.m32(),
                t.m33(),
            )
            t.rotate(self.tilt_y, Qt.Axis.YAxis)
            t.rotate(self.tilt_x, Qt.Axis.XAxis)
        if self.orient or self.spin:
            t.rotate(self.orient + self.spin)
        if self.lift != 1.0:
            t.scale(self.lift, self.lift)
        t.translate(-cx, -cy)
        return t

    def snapshot(self):
        """The channel values, for deciding whether a card needs a new transform."""
        return (
            self.orient,
            self.tilt_x,
            self.tilt_y,
            self.drift_x,
            self.drift_y,
            self.spin,
            self.lift,
        )


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
