"""A fire-like light under the next card to turn"""

import itertools
import math
import random
from functools import cache, lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QRadialGradient, qAlpha
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.motion import _box_blur, drift_phases

FLARE_S = 0.15
COLLAPSE_S = 0.3
FADE_IN_S = 0.35
# A flare's brightness on top of the steady light, from its peak down to where the collapse starts
FLARE_PEAK = 1.2
FLARE_FLOOR = 0.4
# How much the bloom grows at the flare's peak, per unit of brightness over 1
FLARE_GROW = 0.12
COLLAPSE_SHRINK = 0.5
# Sparks age this many times faster while the halo collapses
COLLAPSE_AGEING = 3.0

BLOOM_PAD = 96
BLOOM_DOWNSAMPLE = 8
BLOOM_RADIUS = 3
BLOOM_PASSES = 3
BLOOM_RGB = (255, 140, 40)
BLOOM_OPACITY = 0.85
# The silhouette blurred into the bloom is this much bigger than the card on each side
BLOOM_SPILL = 6

PARTICLES = 60
LIFE_S = (0.6, 1.0)
NUM_SPRITES = 24
SPRITE_PX = 32
# In screen px, whatever the zoom
RISE_PX_S = (30.0, 75.0)
SWAY_PX_S = 12.0
SWAY_HZ = 5.0 / math.tau
SIZE_PX = (5.0, 12.0)
# Sparks are born this much outside the card's edge, so the edge itself burns
BIRTH_OUTSET = 1.03
# A spark shrinks to this share of its size by the end of its life
SPARK_END_SIZE = 0.4

FLICKER_BASE_HZ = 1.3
FLICKER_RATIO = 2.17
FLICKER_OCTAVES = 4
FLICKER_DEPTH = 0.18
# The light without flicker: the flicker's mean
STEADY = 1.0 - FLICKER_DEPTH

# The flame's hot-to-cool ramp
RAMP = (
    (0.0, (255, 244, 214)),
    (0.35, (255, 170, 60)),
    (0.7, (190, 50, 12)),
    (1.0, (120, 20, 5)),
)


def _ramp(u):
    for (u0, c0), (u1, c1) in itertools.pairwise(RAMP):
        if u <= u1:
            k = (u - u0) / (u1 - u0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1, strict=True))
    return RAMP[-1][1]


@cache
def sprites():
    """One soft round spark per step along the ramp"""
    baked = []
    for i in range(NUM_SPRITES):
        u = i / (NUM_SPRITES - 1)
        r, g, b = _ramp(u)
        alpha = (1.0 - u) ** 1.2
        image = QImage(SPRITE_PX, SPRITE_PX, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = SPRITE_PX / 2.0
        gradient = QRadialGradient(QPointF(half, half), half)
        gradient.setColorAt(0.0, QColor(r, g, b, round(255 * alpha)))
        gradient.setColorAt(0.45, QColor(r, g, b, round(128 * alpha)))
        gradient.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QRectF(0, 0, SPRITE_PX, SPRITE_PX))
        painter.end()
        baked.append(QPixmap.fromImage(image))
    return tuple(baked)


@lru_cache(maxsize=8)
def build_bloom(width, height):
    """A warm blurred card silhouette, made the way the contact shadow is"""
    full_w = width + 2 * BLOOM_PAD
    full_h = height + 2 * BLOOM_PAD
    small_w = max(1, full_w // BLOOM_DOWNSAMPLE)
    small_h = max(1, full_h // BLOOM_DOWNSAMPLE)
    small = QImage(small_w, small_h, QImage.Format.Format_ARGB32)
    small.fill(0)
    painter = QPainter(small)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    d = BLOOM_DOWNSAMPLE
    spill = BLOOM_SPILL
    painter.drawRect(
        QRectF(
            (BLOOM_PAD - spill) / d,
            (BLOOM_PAD - spill) / d,
            (width + 2 * spill) / d,
            (height + 2 * spill) / d,
        )
    )
    painter.end()

    alpha = [qAlpha(small.pixel(x, y)) for y in range(small_h) for x in range(small_w)]
    for _ in range(BLOOM_PASSES):
        alpha = _box_blur(alpha, small_w, small_h, BLOOM_RADIUS)

    tinted = QImage(small_w, small_h, QImage.Format.Format_ARGB32)
    r, g, b = BLOOM_RGB
    for y in range(small_h):
        row = y * small_w
        for x in range(small_w):
            tinted.setPixelColor(x, y, QColor(r, g, b, alpha[row + x]))
    return QPixmap.fromImage(
        tinted.scaled(
            full_w,
            full_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


class Flicker:
    """A 1/f sum of sines at a candle's rate"""

    def __init__(self, seed):
        self._phases = drift_phases(seed, FLICKER_OCTAVES)
        self._sum = sum(0.5**k for k in range(FLICKER_OCTAVES))

    def value(self, t):
        total = 0.0
        for k, phase in enumerate(self._phases):
            total += 0.5**k * math.sin(math.tau * FLICKER_BASE_HZ * FLICKER_RATIO**k * t + phase)
        return total / self._sum


class Particle:
    __slots__ = ("age", "life", "size", "sway", "vx", "vy", "x", "y")

    def __init__(self, x, y, life, px):
        # px is scene units per screen pixel
        self.x = x
        self.y = y
        self.vx = random.uniform(-SWAY_PX_S, SWAY_PX_S) * 0.5 * px
        self.vy = -random.uniform(*RISE_PX_S) * px
        self.age = 0.0
        self.life = life
        self.size = random.uniform(*SIZE_PX) * px
        self.sway = random.uniform(0.0, math.tau)


def _half_extents(width, height, degrees):
    """Half the width and height of a width by height rectangle's bounding box, turned by degrees"""
    c = abs(math.cos(math.radians(degrees)))
    s = abs(math.sin(math.radians(degrees)))
    return (c * width + s * height) / 2.0, (s * width + c * height) / 2.0


class HaloItem(QGraphicsItem):
    """The light under one card."""

    # A light, not a thing on the table
    frames_home = False

    def __init__(self, view, on_move):
        super().__init__()
        self._view = view
        self._on_move = on_move
        self.card = None
        self.pending = None
        self.level = 0.0
        self.brightness = STEADY
        self.boost = 0.0
        self.flare_left = 0.0
        self.collapse = None
        self.particles = []
        self._birth_debt = 0.0
        self._flicker = Flicker("halo")
        self._bloom = QPixmap()
        self._bounds = QRectF()
        self._px = 1.0
        self._angle = 0.0
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    def boundingRect(self):
        return self._bounds

    # -- where it is ----------------------------------------------------------------

    def attach(self, card, fade):
        """Fade in under a card"""
        self.card = card
        self.pending = None
        self.particles = []
        self.collapse = None
        self.flare_left = 0.0
        self.boost = 0.0
        self.brightness = STEADY
        if card is None:
            self.setVisible(False)
            self._on_move(None)
            return
        rect = card.boundingRect()
        self._bloom = build_bloom(round(rect.width()), round(rect.height()))
        self.level = 0.0 if fade else 1.0
        self._follow()
        self._update_bounds()
        self.setVisible(True)
        self.update()
        self._on_move(card)

    def flare(self, pending, animate):
        """The card is turning: brighten, collapse into it, then move to pending"""
        if not animate or self.card is None:
            self.attach(pending, fade=animate)
            return
        self.pending = pending
        self.flare_left = FLARE_S
        self.collapse = None

    def settle(self):
        """Finish any flare or fade at once and drop the sparks"""
        if self.flare_left > 0.0 or self.collapse is not None:
            self.attach(self.pending, fade=False)
            return
        if self.card is not None:
            self.level = 1.0
            self.brightness = STEADY
            self.particles = []
            self.update()

    def _follow(self):
        card = self.card
        self.setPos(card.pos() + card.boundingRect().center())
        self.setZValue(card.zValue() - 0.25)

    # -- how bright --------------------------------------------------------------------

    def fade(self):
        """How far in it has faded and not yet collapsed, 0 to 1"""
        if self.card is None:
            return 0.0
        return self.level * (1.0 - (self.collapse or 0.0))

    def light(self):
        """How bright it is now, flicker and flare included; 0 with no card"""
        return max(0.0, self.brightness * self.fade())

    def glow(self):
        """light() without the flicker"""
        return max(0.0, (STEADY + self.boost) * self.fade())

    def is_steady(self):
        """Whether nothing changes from here on but the flicker and the sparks"""
        return self.card is None or (
            self.level >= 1.0 and self.flare_left <= 0.0 and self.collapse is None
        )

    # -- each frame ------------------------------------------------------------------------

    def advance(self, t, dt, lively):
        """Step the fade, flare and collapse; lively adds the flicker and the sparks"""
        if self.card is None:
            return
        self._follow()
        scale = abs(self._view.transform().m11()) or 1.0
        angle = self.card.motion.drawn_angle()
        if abs(scale * self._px - 1.0) > 0.1 or angle != self._angle:
            self._update_bounds()
        if self.level < 1.0 and self.collapse is None:
            self.level = min(1.0, self.level + dt / FADE_IN_S)

        self.boost = 0.0
        if self.flare_left > 0.0:
            self.flare_left -= dt
            self.boost = (FLARE_PEAK - FLARE_FLOOR) * max(0.0, self.flare_left) / FLARE_S
            self.boost += FLARE_FLOOR
            if self.flare_left <= 0.0:
                self.collapse = 0.0
        elif self.collapse is not None:
            self.collapse += dt / COLLAPSE_S
            if self.collapse >= 1.0:
                self.update()
                self.attach(self.pending, fade=True)
                return

        flicker = FLICKER_DEPTH * self._flicker.value(t) if lively else 0.0
        self.brightness = STEADY + flicker + self.boost
        if lively:
            self._step_particles(dt)
        elif self.particles:
            self.particles = []
        self.update()

    def _step_particles(self, dt):
        ageing = COLLAPSE_AGEING if self.collapse is not None else 1.0
        sway = SWAY_PX_S * self._px
        alive = []
        for p in self.particles:
            p.age += dt * ageing
            if p.age >= p.life:
                continue
            p.sway += dt * SWAY_HZ * math.tau
            p.x += (p.vx + sway * math.sin(p.sway)) * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

        if self.collapse is not None:
            return
        mean_life = (LIFE_S[0] + LIFE_S[1]) / 2.0
        self._birth_debt += PARTICLES / mean_life * dt * self.level
        edge = self.card.mapToScene(self.card.boundingRect())
        origin = self.pos()
        while self._birth_debt >= 1.0 and len(self.particles) < PARTICLES:
            self._birth_debt -= 1.0
            i = random.randrange(4)
            a, b = edge[i], edge[(i + 1) % 4]
            k = random.random()
            x = (a.x() + (b.x() - a.x()) * k - origin.x()) * BIRTH_OUTSET
            y = (a.y() + (b.y() - a.y()) * k - origin.y()) * BIRTH_OUTSET
            self.particles.append(Particle(x, y, random.uniform(*LIFE_S), self._px))
        self._birth_debt = min(self._birth_debt, 1.0)

    def _update_bounds(self):
        """The bloom at its biggest, and the sparks' whole rise, at this zoom and angle"""
        scale = abs(self._view.transform().m11()) or 1.0
        self._px = px = 1.0 / scale
        self._angle = angle = self.card.motion.drawn_angle()
        grow = 1.0 + FLARE_GROW * (STEADY + FLICKER_DEPTH + FLARE_PEAK - 1.0)
        bx, by = _half_extents(self._bloom.width() * grow, self._bloom.height() * grow, angle)
        rect = self.card.boundingRect()
        cx, cy = _half_extents(rect.width() * BIRTH_OUTSET, rect.height() * BIRTH_OUTSET, angle)
        # Generously: the card lifts as it turns
        cx, cy = cx * 1.1, cy * 1.1
        side = (SIZE_PX[1] + SWAY_PX_S * 2.0 * LIFE_S[1]) * px
        rise = (RISE_PX_S[1] * LIFE_S[1] + SIZE_PX[1]) * px
        sparks = QRectF(-cx - side, -cy - rise, 2 * (cx + side), 2 * cy + rise + side)
        bounds = QRectF(-bx, -by, 2 * bx, 2 * by).united(sparks)
        if bounds != self._bounds:
            self.prepareGeometryChange()
            self._bounds = bounds

    def paint(self, painter, option, widget=None):
        bright = self.light()
        if bright <= 0.0:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        painter.save()
        collapse = self.collapse or 0.0
        scale = 1.0 + FLARE_GROW * max(0.0, self.brightness - 1.0) - COLLAPSE_SHRINK * collapse
        painter.rotate(self.card.motion.drawn_angle())
        painter.scale(scale, scale)
        painter.setOpacity(min(1.0, BLOOM_OPACITY * bright))
        painter.drawPixmap(
            QPointF(-self._bloom.width() / 2.0, -self._bloom.height() / 2.0), self._bloom
        )
        painter.restore()

        if not self.particles:
            return
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(min(1.0, bright))
        baked = sprites()
        source = QRectF(0, 0, SPRITE_PX, SPRITE_PX)
        for p in self.particles:
            u = p.age / p.life
            sprite = baked[min(NUM_SPRITES - 1, int(u * NUM_SPRITES))]
            s = p.size * (1.0 - (1.0 - SPARK_END_SIZE) * u)
            painter.drawPixmap(QRectF(p.x - s, p.y - s, 2 * s, 2 * s), sprite, source)
