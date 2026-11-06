"""A throwaway spike: deal a spread face-down and turn it card by card under a halo.

Never merged, saves nothing. Knobs for trying the brief's questions, read once when the tab opens:

    TAROT_SPIKE_DEAL=z            deal in ascending z instead of number order
    TAROT_SPIKE_TURN=deal         turn in deal order instead of number (reading) order
    TAROT_SPIKE_DECK_SIZE=N       cut the deck to its first N cards (a short deal)
    TAROT_SPIKE_SIGNIFICATOR=id   stage that card face-up in position 1 before Deal
    TAROT_SPIKE_REVERSED=all|none force every draw reversed or upright
    TAROT_SPIKE_PARTICLES=N       the halo's particle count (default 60)
    TAROT_SPIKE_LIFE=a,b          a particle's life in seconds (default 0.6,1.0)
    TAROT_SPIKE_FRAMES=1          log paint ms per frame for the view, every 2 s

Deal is the pane's button, the canvas's Summon (D), or a double-click on the empty canvas. Cards fly
in face-down from below the bottom edge of the view, where the reader sits.

A card already on a slot when Deal is pressed (dropped, pasted or summoned there) fills that slot by
hand: it is snapped in and its card is taken out of the draw.
"""

import glob
import itertools
import math
import os
import random
import time

from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QSignalBlocker,
    QSize,
    Qt,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QFontMetricsF,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
    qAlpha,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsItem,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStyle,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas import DraggableCardItem, SlotItem
from tarot_canvas.ui.canvas.motion import (
    EXTRA_PERSPECTIVE_PER_DEGREE,
    TICK_MS,
    MotionChannels,
    _box_blur,
    drift_phases,
)
from tarot_canvas.ui.canvas.spread_pane import MeaningRole, NumberRole, PositionDelegate, _draw
from tarot_canvas.ui.library import units
from tarot_canvas.ui.strings import CANVAS, READING_SPIKE
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tarot_canvas.ui.widgets.reorder_list import GRIP_WIDTH
from tarot_canvas.utils.logger import logger

# -- timings, in seconds -----------------------------------------------------

DEAL_GAP_S = 0.12
FLIGHT_S = 0.42
TURN_S = 0.5
TURN_LIFT = 1.10
TURN_ALL_GAP_S = 0.15
FLARE_S = 0.15
COLLAPSE_S = 0.3
HALO_FADE_IN_S = 0.35
CANDLE_IN_S = 0.6
CANDLE_OUT_S = 1.0

# -- the deal -----------------------------------------------------------------

CARD_Z = 10000.0
FLIGHT_Z = 30000.0
# The next card lies on top until it is turned, so a covered position (Celtic Cross 1) can be clicked
NEXT_Z = 40000.0
TURNING_Z = 40001.0

# -- the halo -----------------------------------------------------------------

BLOOM_PAD = 96
BLOOM_DOWNSAMPLE = 8
BLOOM_RADIUS = 3
BLOOM_PASSES = 3
BLOOM_RGB = (255, 140, 40)
BLOOM_OPACITY = 0.85

PARTICLES = int(os.environ.get("TAROT_SPIKE_PARTICLES", "60"))
LIFE = tuple(float(x) for x in os.environ.get("TAROT_SPIKE_LIFE", "0.6,1.0").split(","))
SPRITES = 24
SPRITE_PX = 32
RISE_PX_S = (30.0, 75.0)
SWAY_PX_S = 12.0
SIZE_PX = (5.0, 12.0)

FLICKER_BASE_HZ = 1.3
FLICKER_RATIO = 2.17
FLICKER_OCTAVES = 4
FLICKER_DEPTH = 0.18

# The flame's hot-to-cool ramp: near-white, amber, deep red, gone
RAMP = (
    (0.0, (255, 244, 214)),
    (0.35, (255, 170, 60)),
    (0.7, (190, 50, 12)),
    (1.0, (120, 20, 5)),
)

# -- the candle -----------------------------------------------------------------

CANDLE_ALPHA = 0.8
CANDLE_REACH = 1.42  # of the table's half-size, where the dark is whole
WARM_PATCH_REACH = 1.25  # of the haloed card's longer side
WARM_PATCH_ALPHA = 60


def _ease_in_out(u):
    return u * u * (3.0 - 2.0 * u)


def _ease_out(u):
    return 1.0 - (1.0 - u) ** 3


def _centre(item):
    return item.pos() + item.boundingRect().center()


def _ramp(u):
    for (u0, c0), (u1, c1) in itertools.pairwise(RAMP):
        if u <= u1:
            k = (u - u0) / (u1 - u0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1, strict=True))
    return RAMP[-1][1]


def _sprites():
    """One soft round spark per step along the ramp, premultiplied for Plus"""
    sprites = []
    for i in range(SPRITES):
        u = i / (SPRITES - 1)
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
        sprites.append(QPixmap.fromImage(image))
    return sprites


_bloom_cache = {}


def build_bloom(width, height):
    """A warm blurred card silhouette, made the way build_contact_shadow makes a shadow"""
    key = (int(width), int(height))
    if key in _bloom_cache:
        return _bloom_cache[key]
    full_w = int(width) + 2 * BLOOM_PAD
    full_h = int(height) + 2 * BLOOM_PAD
    small_w = max(1, full_w // BLOOM_DOWNSAMPLE)
    small_h = max(1, full_h // BLOOM_DOWNSAMPLE)
    small = QImage(small_w, small_h, QImage.Format.Format_ARGB32)
    small.fill(0)
    painter = QPainter(small)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    d = BLOOM_DOWNSAMPLE
    painter.drawRect(
        QRectF((BLOOM_PAD - 6) / d, (BLOOM_PAD - 6) / d, (width + 12) / d, (height + 12) / d)
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
    pixmap = QPixmap.fromImage(
        tinted.scaled(
            full_w,
            full_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    _bloom_cache[key] = pixmap
    return pixmap


class Flicker:
    """PinkOscillator's sum, at a candle's rate rather than a card's drift"""

    def __init__(self, seed):
        self._phases = drift_phases(seed, FLICKER_OCTAVES)
        self._sum = sum(0.5**k for k in range(FLICKER_OCTAVES))

    def value(self, t):
        total = 0.0
        for k, phase in enumerate(self._phases):
            total += 0.5**k * math.sin(math.tau * FLICKER_BASE_HZ * FLICKER_RATIO**k * t + phase)
        return total / self._sum


# -- the deck's back ------------------------------------------------------------


def back_path(deck):
    """The deck's default back, or any back it has, or None"""
    if deck is None:
        return None
    backs, default = deck.get_card_backs()
    if default in backs:
        return backs[default]
    # get_card_backs globs *.png only; the reference deck's back is classic.jpg
    folder = os.path.join(deck.deck_path, "card_backs")
    for extension in ("png", "jpg", "jpeg", "webp"):
        path = os.path.join(folder, f"{default}.{extension}")
        if os.path.exists(path):
            return path
    found = sorted(glob.glob(os.path.join(folder, "*.*")))
    return found[0] if found else (next(iter(backs.values())) if backs else None)


def back_pixmap(deck, size):
    """The deck's back at size, or a plain drawn card"""
    path = back_path(deck)
    if path:
        source = QPixmap(path)
        if not source.isNull():
            return source.scaled(
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(58, 36, 48))
    painter.setPen(QPen(QColor(140, 112, 80), 3))
    radius = size.width() * 0.05
    painter.drawRoundedRect(QRectF(1.5, 1.5, size.width() - 3, size.height() - 3), radius, radius)
    painter.end()
    return pixmap


# -- a card that can lie face-down -----------------------------------------------


class ReadingMotion(MotionChannels):
    """MotionChannels plus a turn about the card's own vertical axis"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.flip = 0.0

    def compose(self, width, height):
        cx, cy = width / 2.0, height / 2.0
        tilt_x = self.tilt_x + self.face_x
        tilt_y = self.tilt_y + self.face_y
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
        spin = self.drawn_angle()
        if spin:
            t.rotate(spin)
        if self.flip:
            # A reversed face is drawn turned 180°, so its vertical axis points the other way
            t.rotate(-self.flip if self.reversed else self.flip, Qt.Axis.YAxis)
        if self.lift != 1.0:
            t.scale(self.lift, self.lift)
        t.translate(-cx, -cy)
        return t

    def at_rest(self):
        return super().at_rest() and self.flip == 0.0

    def snapshot(self):
        return (*super().snapshot(), self.flip)


class ReadingCard(DraggableCardItem):
    """A dealt card: face-down until its turn, then an ordinary canvas card"""

    def __init__(self, pixmap, card, tab, deck, reversed, back):
        super().__init__(pixmap, card, tab, deck=deck, reversed=False)
        self.motion = ReadingMotion()
        self._applied = None
        self._applied_corners = None
        # Decided at the draw; not drawn until the turn, or a reversed back would tell
        self.drawn_reversed = reversed
        self.face_down = True
        self.slot = None
        self._face = pixmap
        self._turning = None
        self.setPixmap(back)
        self.set_interactive(False)
        self._apply_motion()

    def set_interactive(self, interactive):
        flags = QGraphicsItem.GraphicsItemFlag
        self.setFlag(flags.ItemIsMovable, interactive)
        self.setFlag(flags.ItemIsSelectable, interactive)
        self.setAcceptHoverEvents(interactive)
        self.setCursor(Qt.CursorShape.OpenHandCursor if interactive else Qt.CursorShape.ArrowCursor)

    def set_next(self, is_next):
        """Only the next card to turn answers the pointer"""
        if not self.face_down:
            return
        self.setAcceptHoverEvents(is_next)
        self.setCursor(Qt.CursorShape.PointingHandCursor if is_next else Qt.CursorShape.ArrowCursor)
        if not is_next:
            self.end_hover()

    def mark_colour(self):
        # The tab icon would otherwise show the suit's colour before the turn
        return QColor(110, 96, 90) if self.face_down else super().mark_colour()

    def set_detail(self, device_scale):
        # A sharper level is the face's art
        if not self.face_down:
            super().set_detail(device_scale)

    def is_turning(self):
        return self._turning is not None

    def begin_turn(self, animate):
        if not animate:
            self._reveal()
            self.motion.flip = 0.0
            self._apply_motion()
            self.parent_tab.card_turned(self)
            return
        self._turning = 0.0
        self._lift.snap(TURN_LIFT)
        self.motion.lift = TURN_LIFT
        self._apply_motion()

    def _reveal(self):
        self.face_down = False
        self.motion.reversed = self.drawn_reversed
        self._wanted_level = 1
        self._show_level(1, self._face)
        self.end_hover()
        self.set_interactive(True)
        self._schedule_tab_icon()
        self.parent_tab.schedule_detail()
        self.parent_tab.refresh_rows()

    def advance_motion(self, t, dt, ambient_gain, view_scale=1.0):
        if self._turning is not None:
            self._turning += dt
            u = min(1.0, self._turning / TURN_S)
            angle = 180.0 * _ease_in_out(u)
            if angle >= 90.0 and self.face_down:
                self._reveal()
            self.motion.flip = angle if self.face_down else angle - 180.0
            if u >= 1.0:
                self.motion.flip = 0.0
                self._turning = None
                self.parent_tab.card_turned(self)
        return super().advance_motion(t, dt, ambient_gain, view_scale)

    def settle_motion(self):
        if self._turning is not None:
            if self.face_down:
                self._reveal()
            self.motion.flip = 0.0
            self._turning = None
            self.parent_tab.card_turned(self)
        return super().settle_motion()

    def mousePressEvent(self, event):
        if self.face_down:
            event.accept()
            if event.button() == Qt.MouseButton.LeftButton:
                self.parent_tab.card_clicked(self)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.face_down:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.face_down:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.face_down:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


# -- the halo ---------------------------------------------------------------------


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size", "sway")

    def __init__(self, x, y, life, px):
        # px is scene units per screen pixel: a spark is the same size and speed at any zoom
        self.x = x
        self.y = y
        self.vx = random.uniform(-SWAY_PX_S, SWAY_PX_S) * 0.5 * px
        self.vy = -random.uniform(*RISE_PX_S) * px
        self.age = 0.0
        self.life = life
        self.size = random.uniform(*SIZE_PX) * px
        self.sway = random.uniform(0.0, math.tau)


class HaloItem(QGraphicsItem):
    """A fire-like light under the next card to turn: a warm bloom and rising sparks"""

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.card = None
        self.level = 0.0
        self.brightness = 1.0
        self.flare_left = 0.0
        self.collapse = None
        self.pending = None
        self.particles = []
        self._birth_debt = 0.0
        self._flicker = Flicker("halo")
        self._sprites = _sprites()
        self._bloom = QPixmap()
        self._reach = 1.0
        self._px = 1.0
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    def boundingRect(self):
        return QRectF(-self._reach, -self._reach, 2 * self._reach, 2 * self._reach)

    def attach(self, card, fade):
        """Sit under card, or hide with None"""
        self.prepareGeometryChange()
        self.card = card
        self.particles = []
        self.collapse = None
        self.flare_left = 0.0
        self.tab.caption.show_for(card)
        self.tab.update_caption()
        if card is None:
            self.setVisible(False)
            return
        self.tab.set_caption_opacity(0.0 if fade else 1.0)
        rect = card.boundingRect()
        self._bloom = build_bloom(rect.width(), rect.height())
        self._update_reach()
        self.setPos(_centre(card))
        self.setZValue(card.zValue() - 0.25)
        self.level = 0.0 if fade else 1.0
        self.setVisible(True)
        self.update()

    def _update_reach(self):
        """Room for the bloom, the warm patch, and a spark's whole rise at this zoom"""
        scale = abs(self.tab.view.transform().m11()) or 1.0
        self._px = 1.0 / scale
        rect = self.card.boundingRect()
        bloom_reach = math.hypot(self._bloom.width(), self._bloom.height()) / 2.0 * 1.2
        patch_reach = max(rect.width(), rect.height()) * WARM_PATCH_REACH
        rise = (RISE_PX_S[1] * LIFE[1] + SIZE_PX[1] + SWAY_PX_S) * self._px
        reach = max(bloom_reach, patch_reach) + rise
        if reach != self._reach:
            self.prepareGeometryChange()
            self._reach = reach

    def flare(self, pending, animate):
        """The card was clicked: brighten, collapse into it, then move to pending"""
        if not animate:
            self.attach(pending, fade=False)
            return
        self.pending = pending
        self.flare_left = FLARE_S
        self.collapse = None

    def advance(self, t, dt, full):
        if self.card is None:
            return
        self.setPos(_centre(self.card))
        self.setZValue(self.card.zValue() - 0.25)
        scale = abs(self.tab.view.transform().m11()) or 1.0
        if abs(scale * self._px - 1.0) > 0.1:
            self._update_reach()
        if self.level < 1.0 and self.collapse is None:
            self.level = min(1.0, self.level + dt / HALO_FADE_IN_S)

        boost = 0.0
        if self.flare_left > 0.0:
            self.flare_left -= dt
            boost = 0.8 * max(0.0, self.flare_left) / FLARE_S + 0.4
            if self.flare_left <= 0.0:
                self.collapse = 0.0
        elif self.collapse is not None:
            self.collapse += dt / COLLAPSE_S
            if self.collapse >= 1.0:
                self.attach(self.pending, fade=True)
                self.pending = None
                return

        self.tab.set_caption_opacity(self.level * (1.0 - (self.collapse or 0.0)))
        flicker = FLICKER_DEPTH * self._flicker.value(t) if full else 0.0
        self.brightness = 1.0 - FLICKER_DEPTH + flicker + boost

        if full:
            self._step_particles(dt)
        self.update()

    def _step_particles(self, dt):
        ageing = 3.0 if self.collapse is not None else 1.0
        alive = []
        for p in self.particles:
            p.age += dt * ageing
            if p.age >= p.life:
                continue
            p.sway += dt * 5.0
            p.x += (p.vx + SWAY_PX_S * self._px * math.sin(p.sway)) * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

        if self.collapse is not None:
            return
        mean_life = (LIFE[0] + LIFE[1]) / 2.0
        self._birth_debt += PARTICLES / mean_life * dt * self.level
        edge = self.card.mapToScene(self.card.boundingRect())
        origin = self.pos()
        while self._birth_debt >= 1.0 and len(self.particles) < PARTICLES:
            self._birth_debt -= 1.0
            i = random.randrange(4)
            a, b = edge[i], edge[(i + 1) % 4]
            k = random.random()
            x = a.x() + (b.x() - a.x()) * k - origin.x()
            y = a.y() + (b.y() - a.y()) * k - origin.y()
            # A little outward, so the edge itself burns
            self.particles.append(Particle(x * 1.03, y * 1.03, random.uniform(*LIFE), self._px))
        self._birth_debt = min(self._birth_debt, 1.0)

    def paint(self, painter, option, widget=None):
        if self.card is None:
            return
        fade = self.level * (1.0 - (self.collapse or 0.0))
        bright = self.brightness * fade
        if bright <= 0.0:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # The warm light thrown on the table
        rect = self.card.boundingRect()
        patch = max(rect.width(), rect.height()) * WARM_PATCH_REACH
        gradient = QRadialGradient(QPointF(0, 0), patch)
        alpha = min(255, round(WARM_PATCH_ALPHA * bright * self.tab.candle_level()))
        gradient.setColorAt(0.0, QColor(255, 150, 60, alpha))
        gradient.setColorAt(0.5, QColor(255, 120, 40, alpha // 3))
        gradient.setColorAt(1.0, QColor(255, 120, 40, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), patch, patch)

        # The bloom
        painter.save()
        scale = 1.0 + 0.12 * max(0.0, self.brightness - 1.0) - 0.5 * (self.collapse or 0.0)
        painter.rotate(self.card.motion.drawn_angle())
        painter.scale(scale, scale)
        painter.setOpacity(min(1.0, BLOOM_OPACITY * bright))
        painter.drawPixmap(
            QPointF(-self._bloom.width() / 2.0, -self._bloom.height() / 2.0), self._bloom
        )
        painter.restore()

        # The sparks
        if not self.particles:
            return
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(min(1.0, bright))
        source = QRectF(0, 0, SPRITE_PX, SPRITE_PX)
        for p in self.particles:
            u = p.age / p.life
            sprite = self._sprites[min(SPRITES - 1, int(u * SPRITES))]
            s = p.size * (1.0 - 0.6 * u)
            painter.drawPixmap(QRectF(p.x - s, p.y - s, 2 * s, 2 * s), sprite, source)


# -- the caption ---------------------------------------------------------------------

CAPTION_WIDTH_PX = 300
CAPTION_GAP_PX = 10
CAPTION_PAD_PX = 8
CAPTION_FILL = QColor(20, 14, 10, 200)
CAPTION_TEXT = QColor(255, 240, 220)
CAPTION_MEANING = QColor(225, 205, 185)
CAPTION_Z = 50000.0
MEANING_LINES = 2


class CaptionItem(QGraphicsItem):
    """The next card's position under it, at screen size: its number, label and meaning.

    The spread's own words, so nothing here is new copy
    """

    def __init__(self):
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(CAPTION_Z)
        self.setVisible(False)
        self._slot = None
        self._rect = QRectF()
        self._title_font = typography.font(typography.Role.BODY)
        self._title_font.setBold(True)
        self._small_font = typography.font(typography.Role.SMALL)

    def show_for(self, card):
        """Sit under card's position, or hide with None"""
        self.prepareGeometryChange()
        slot = getattr(card, "slot", None)
        self._slot = slot
        if slot is None:
            self.setVisible(False)
            return
        title = QFontMetricsF(self._title_font)
        small = QFontMetricsF(self._small_font)
        badge = title.height()
        text_width = CAPTION_WIDTH_PX - 3 * CAPTION_PAD_PX - badge
        label_width = min(text_width, title.horizontalAdvance(slot.label))
        meaning = " ".join(slot.meaning.split())
        meaning_width = min(text_width, small.horizontalAdvance(meaning)) if meaning else 0.0
        lines = 0
        if meaning:
            lines = min(MEANING_LINES, math.ceil(small.horizontalAdvance(meaning) / text_width))
        width = 3 * CAPTION_PAD_PX + badge + max(label_width, meaning_width)
        height = 2 * CAPTION_PAD_PX + title.height() + lines * small.lineSpacing()
        self._rect = QRectF(-width / 2.0, CAPTION_GAP_PX, width, height)
        self._lines = lines
        self.place()
        self.setVisible(True)
        self.update()

    def slot_rect(self):
        return self._slot.sceneBoundingRect() if self._slot is not None else QRectF()

    def place(self):
        if self._slot is not None:
            rect = self._slot.sceneBoundingRect()
            self.setPos(rect.center().x(), rect.bottom())

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        slot = self._slot
        if slot is None:
            return
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        rect = self._rect
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(CAPTION_FILL)
        painter.drawRoundedRect(rect, CAPTION_PAD_PX, CAPTION_PAD_PX)

        title = QFontMetricsF(self._title_font)
        badge = title.height()
        top = rect.top() + CAPTION_PAD_PX
        circle = QRectF(rect.left() + CAPTION_PAD_PX, top, badge, badge)
        painter.setBrush(NEXT_BAR)
        painter.drawEllipse(circle)
        painter.setFont(self._title_font)
        painter.setPen(QColor(30, 18, 8))
        painter.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), str(slot.number))

        left = circle.right() + CAPTION_PAD_PX
        width = rect.right() - CAPTION_PAD_PX - left
        painter.setPen(CAPTION_TEXT)
        painter.drawText(
            QRectF(left, top, width, title.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title.elidedText(slot.label, Qt.TextElideMode.ElideRight, width),
        )
        if self._lines:
            small = QFontMetricsF(self._small_font)
            meaning = " ".join(slot.meaning.split())
            # Wrapped into its lines; only a meaning too long for them is elided
            fitted = meaning
            if small.horizontalAdvance(meaning) > width * self._lines:
                room = width * self._lines - small.averageCharWidth() * 4 * (self._lines - 1)
                fitted = small.elidedText(meaning, Qt.TextElideMode.ElideRight, room)
            painter.setFont(self._small_font)
            painter.setPen(CAPTION_MEANING)
            painter.drawText(
                QRectF(left, top + title.height(), width, self._lines * small.lineSpacing()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                fitted,
            )


# -- the model ---------------------------------------------------------------------------


class Placement:
    """One position of the spread and the card that fills it.

    The slot on the canvas, the row in the pane and the card are three views of this. The slot is drawn
    only while nothing fills the position; the card carries the position wherever it is moved, and
    selecting the card or the row selects the other
    """

    def __init__(self, slot):
        self.slot = slot
        self.card = None

    def fill(self, card):
        self.card = card
        card.placement = self

    def empty(self):
        self.card = None

    def sync_slot(self, landed):
        """The slot shows only while no card has landed on it"""
        shown = self.card is None or not landed
        self.slot.setVisible(shown)
        # The shadow is its own item in the scene, so it is hidden with the slot or it stays behind
        self.slot.shadow.setVisible(shown)


# -- paint timing -------------------------------------------------------------------


REVEAL_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)


class RevealKeys(QObject):
    """Enter or Space on the canvas or the pane's list turns the next card.

    Watched on those two only, so a space typed into the question is still a space
    """

    def __init__(self, tab, watched):
        super().__init__(tab)
        self.tab = tab
        for widget in watched:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in REVEAL_KEYS
            and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            and self.tab.phase == "dealt"
            and self.tab.has_next()
        ):
            if not event.isAutoRepeat():
                self.tab.turn_next()
            return True
        return False


class PaintTimer(QObject):
    """ms per paint of the view, logged every 2 s"""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._start = None
        self._samples = []
        self._last = time.perf_counter()
        view.viewport().installEventFilter(self)
        view.foreground_hooks.append(self._end)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Paint:
            self._start = time.perf_counter()
        return False

    def _end(self, painter, rect):
        if self._start is None:
            return
        self._samples.append((time.perf_counter() - self._start) * 1000.0)
        self._start = None
        now = time.perf_counter()
        if now - self._last >= 2.0 and self._samples:
            ordered = sorted(self._samples)
            logger.info(
                f"reading spike paint: n={len(ordered)} median={ordered[len(ordered) // 2]:.2f} ms "
                f"p95={ordered[int(len(ordered) * 0.95)]:.2f} ms particles={PARTICLES}"
            )
            self._samples = []
            self._last = now


# -- the pane's rows ------------------------------------------------------------------

THUMB_RATIO = 0.58
NEXT_FILL = QColor(255, 150, 60, 55)
NEXT_BAR = QColor(230, 130, 40)
NEXT_BAR_PX = 3


class ReadingRowDelegate(PositionDelegate):
    """A position's row with its card in place of the grip, and the next card's row lit"""

    def __init__(self, view, tab):
        super().__init__(view)
        self.tab = tab
        self._open_rows = set()

    # -- open rows: the selected one and the next one show their whole meaning ------------

    def is_open(self, index):
        return index.row() in self._open_rows

    def set_open_rows(self, rows):
        """Open rows, asking the view to re-measure every row that changed"""
        changed = self._open_rows ^ set(rows)
        self._open_rows = set(rows)
        for row in changed:
            self.sizeHintChanged.emit(self.tab.positions.index(row))

    def _meaning(self, index):
        return " ".join((index.data(MeaningRole) or "").split())

    def _meaning_width(self, option):
        """How wide the meaning's lines are in a row as wide as the list"""
        measured = type(option)(option)
        measured.rect = QRect(0, 0, self.view.viewport().width(), 1000)
        return self.title_rect(measured, True).width()

    def _wrapped_height(self, index, width):
        small = typography.font(typography.Role.SMALL)
        bounds = QFontMetrics(small).boundingRect(
            QRect(0, 0, max(1, width), 100000),
            int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
            self._meaning(index),
        )
        return bounds.height()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        if not self.is_open(index) or not self._meaning(index):
            return hint
        title_height, small_height = self._line_heights(option)
        meaning = self._wrapped_height(index, self._meaning_width(option))
        height = title_height + max(small_height, meaning) + 2 * units.LARGE_SPACING
        return QSize(hint.width(), max(hint.height(), height))

    def _paint_text(self, painter, option, index):
        meaning = self._meaning(index)
        if not self.is_open(index) or not meaning:
            return super()._paint_text(painter, option, index)
        title_font, small_font = self._fonts(option, False)
        title = self.title_rect(option, True)
        _draw(
            painter,
            title,
            index.data(Qt.ItemDataRole.DisplayRole),
            title_font,
            option.palette.text().color(),
        )
        painter.setFont(small_font)
        painter.setPen(option.palette.placeholderText().color())
        bottom = option.rect.bottom() - units.LARGE_SPACING
        painter.drawText(
            QRect(title.left(), title.bottom() + 1, title.width(), bottom - title.bottom()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            meaning,
        )
        return None

    def helpEvent(self, event, view, option, index):
        """A closed row whose meaning is cut off shows it whole in a tooltip"""
        if event.type() == QEvent.Type.ToolTip and index.isValid():
            meaning = self._meaning(index)
            small = QFontMetrics(typography.font(typography.Role.SMALL))
            width = self.title_rect(option, True).width()
            if meaning and not self.is_open(index) and small.horizontalAdvance(meaning) > width:
                QToolTip.showText(event.globalPos(), meaning, view)
            else:
                QToolTip.hideText()
            return True
        return super().helpEvent(event, view, option, index)

    def _thumb_rect(self, option):
        title_height, small_height = self._line_heights(option)
        height = title_height + small_height + 2 * (units.LARGE_SPACING - units.SMALL_SPACING)
        left = option.rect.left() + units.SMALL_SPACING + NEXT_BAR_PX
        top = option.rect.top() + units.SMALL_SPACING
        return QRect(left, top, round(height * THUMB_RATIO), height)

    def _number_rect(self, option):
        rect = super()._number_rect(option)
        rect.translate(self._thumb_rect(option).width() + NEXT_BAR_PX - GRIP_WIDTH, 0)
        return rect

    def paint(self, painter, option, index):
        slot = self.tab.slots()[index.row()]
        palette = option.palette
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            selected = QColor(palette.highlight().color())
            selected.setAlpha(70)
            painter.fillRect(option.rect, selected)
        if self.tab.is_next_slot(slot):
            painter.fillRect(option.rect, NEXT_FILL)
            bar = QRect(option.rect.left(), option.rect.top(), NEXT_BAR_PX, option.rect.height())
            painter.fillRect(bar, NEXT_BAR)
        self._paint_text(painter, option, index)
        self._paint_thumb(painter, self._thumb_rect(option), self.tab.card_in(slot), palette)
        number = self._number_rect(option)
        painter.setFont(self._fonts(option, self.tab.is_next_slot(slot))[0])
        painter.setPen(palette.text().color())
        painter.drawText(number, int(Qt.AlignmentFlag.AlignCenter), str(index.data(NumberRole)))
        painter.restore()

    def _paint_thumb(self, painter, rect, card, palette):
        painter.save()
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        target = QRectF(rect)
        if card is None:
            # An empty place
            colour = palette.placeholderText().color()
            painter.setPen(QPen(colour, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = target.width() * 0.08
            painter.drawRoundedRect(target.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        else:
            face_down = getattr(card, "face_down", False)
            pixmap = card.pixmap() if face_down else getattr(card, "_face", card._base)
            if not face_down and card.is_reversed():
                painter.translate(target.center())
                painter.rotate(180)
                painter.translate(-target.center())
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.restore()


# -- the tab -------------------------------------------------------------------------


class ReadingSpikeTab(SpreadTab):
    """A spread opened to deal from: staged, dealt face-down, turned, then an ordinary canvas"""

    TOOLS_TITLE = CANVAS["section_cards"]

    def __init__(self, spread, parent=None):
        super().__init__(spread, None, parent)
        self.phase = "staged"
        self._deal_order = os.environ.get("TAROT_SPIKE_DEAL", "number")
        self._turn_order = os.environ.get("TAROT_SPIKE_TURN", "reading")
        self._ground = QColor(Qt.GlobalColor.darkGray)
        self._candle = 0.0
        self._candle_target = 0.0
        self._flights = []
        self._deal_started = None
        self._turn_queue = []
        self._turn_all_at = None
        self._clock_on = False
        self._now = 0.0
        self.apply_background_settings()

        # The spread is read, not designed, here
        for slot in self._slots:
            slot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            slot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            slot.setAcceptHoverEvents(False)
            slot.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            slot.setCursor(Qt.CursorShape.ArrowCursor)
        self.pane.name_edit.setReadOnly(True)
        self.pane.description_edit.setReadOnly(True)
        self.pane.menu_button.hide()
        self.pane.list_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._build_form()

        self.deck = self._chosen_deck()
        self._back = None
        self._dealt = []
        self.placements = [Placement(slot) for slot in self._slots]
        self._syncing = False
        self._landed = set()
        self._deal_from = QPointF()
        self.rows = ReadingRowDelegate(self.pane.list_view, self)
        self.pane.list_view.setItemDelegate(self.rows)
        self.pane.list_view.selectionModel().selectionChanged.connect(self.refresh_rows)
        # Not in the scene: painted over the candle, which would otherwise dim it near the edges
        self.caption = CaptionItem()
        self.halo = HaloItem(self)
        self.scene.addItem(self.halo)
        self.view.foreground_hooks.append(self._paint_candle)
        self.view.foreground_hooks.append(self._paint_caption)
        self._reveal_keys = RevealKeys(self, (self.view, self.pane.list_view))
        if os.environ.get("TAROT_SPIKE_FRAMES"):
            self._paint_timer = PaintTimer(self.view)
        self._stage_significator()

    # -- the canvas, not the designer -------------------------------------------------

    def bind_commands(self):
        CanvasTab.bind_commands(self)

    def command_handlers(self):
        handlers = CanvasTab.command_handlers(self)
        # Saves nothing
        del handlers["canvas.save_layout_as_spread"]
        return handlers

    def tools(self):
        return CanvasTab.tools(self)

    def on_draw_card(self, at=None):
        # Before the deal, summoning a card deals the spread
        if self.phase == "staged":
            self.deal()
            return
        # After it, from the reading's deck: a card not already on the table
        on_table = {
            card.card_data.get("id")
            for card in self.cards()
            if getattr(card, "deck", None) is self.deck
        }
        pool = [card for card in self._pool() if card.get("id") not in on_table]
        if not pool:
            logger.info("reading spike: every card of the deck is on the table")
            return
        CanvasTab.add_specific_card(
            self, random.choice(pool), self.deck, random.choice([True, False]), at
        )

    def add_specific_card(self, card, card_deck=None, is_reversed=False, at=None):
        return CanvasTab.add_specific_card(self, card, card_deck, is_reversed, at)

    def build_card_menu(self, item):
        if isinstance(item, SlotItem) or getattr(item, "face_down", False):
            return None
        return CanvasTab.build_card_menu(self, item)

    def on_turn_card_by_wheel(self, card, notches, fine):
        if not getattr(card, "face_down", False):
            super().on_turn_card_by_wheel(card, notches, fine)

    def card_menu(self, scene_pos):
        item = self.card_at(scene_pos)
        if item is None or isinstance(item, SlotItem) or getattr(item, "face_down", False):
            return None
        return super().card_menu(scene_pos)

    # -- the model: placements, rows and selection -------------------------------------

    def _placement_at(self, slot):
        return self.placements[self._slots.index(slot)]

    def placement_of(self, card):
        placement = getattr(card, "placement", None)
        return placement if placement is not None and placement.card is card else None

    def cards(self):
        # A filled position's hidden slot is not on the table: nothing snaps to it
        return tuple(card for card in self._cards if card.isVisible())

    def show_selection(self):
        """The canvas's selection, shown as the row of the one selected card's position"""
        if not hasattr(self, "placements"):
            return
        self._sync_delete()
        if self._syncing:
            return
        selected = self.selected_cards()
        placement = self.placement_of(selected[0]) if len(selected) == 1 else None
        view = self.pane.list_view
        self._syncing = True
        try:
            if placement is None:
                view.selectionModel().clearSelection()
            else:
                index = self.positions.index(self.placements.index(placement))
                view.selectionModel().setCurrentIndex(
                    index, QItemSelectionModel.SelectionFlag.ClearAndSelect
                )
                view.scrollTo(index)
        finally:
            self._syncing = False

    def _select_slot(self, row):
        """A row chosen in the pane selects its position's card, once it is face-up"""
        if self._syncing:
            return
        card = self.placements[row].card
        if card is None or card.scene() is None or getattr(card, "face_down", False):
            return
        self._syncing = True
        try:
            with QSignalBlocker(self.scene):
                self.scene.clearSelection()
            card.setSelected(True)
            self.view.ensureVisible(card.sceneBoundingRect(), 40, 40)
        finally:
            self._syncing = False

    # -- deleting: the reading's cards stay; only extras go ----------------------------

    def _extras(self):
        """Selected cards that fill no position: summoned, pasted or dropped after the deal"""
        return [card for card in self.selected_cards() if self.placement_of(card) is None]

    def _sync_delete(self):
        self.commands["canvas.delete"].setEnabled(not self.arranging and bool(self._extras()))

    def can_delete(self):
        return not self.arranging and bool(self._extras())

    def can_cut_card(self):
        return self.can_copy_card() and not self.arranging and bool(self._extras())

    def on_delete_card(self):
        """Remove the selected extras; a card that fills a position is the reading, and stays"""
        extras = self._extras()
        for card in extras:
            self.scene.removeItem(card)
        if extras:
            self.layout_changed.emit()

    def swap_card(self, item, deck, card):
        placement = self.placement_of(item)
        replacement = super().swap_card(item, deck, card)
        if replacement is not None and placement is not None:
            placement.fill(replacement)
            self._landed.add(replacement)
            self.refresh_rows()
        return replacement

    def mark_modified(self):
        pass

    def can_save(self):
        return False

    def has_unsaved_changes(self):
        return False

    def set_ground(self, color):
        super().set_ground(color)
        self._ground = QColor(color)

    # -- the pane -------------------------------------------------------------------------

    def _build_form(self):
        form = QWidget()
        column = QVBoxLayout(form)
        margin = units.LARGE_SPACING
        column.setContentsMargins(margin, 0, margin, margin)
        column.setSpacing(units.SMALL_SPACING)

        self.deck_combo = QComboBox()
        reference = deck_manager.get_reference_deck()
        for deck in deck_manager.get_all_decks():
            self.deck_combo.addItem(deck.get_name(), deck)
            if deck is reference:
                self.deck_combo.setCurrentIndex(self.deck_combo.count() - 1)
        self.deck_combo.currentIndexChanged.connect(self._on_deck_chosen)

        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText(READING_SPIKE["question_hint"])
        self.question_edit.setAccessibleName(READING_SPIKE["question_hint"])

        # Deal plays the reading; Reveal All fast-forwards through the turns that are left
        self.deal_button = QPushButton(
            QIcon.fromTheme("media-playback-start"), READING_SPIKE["deal"]
        )
        self.deal_button.clicked.connect(self.deal)
        self.turn_all_button = QPushButton(
            QIcon.fromTheme("media-seek-forward"), READING_SPIKE["turn_all"]
        )
        self.turn_all_button.clicked.connect(self.turn_all)
        self.turn_all_button.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.deal_button)
        buttons.addWidget(self.turn_all_button)

        column.addWidget(self.deck_combo)
        column.addWidget(self.question_edit)
        column.addLayout(buttons)
        self.pane.body.insertWidget(1, form)

    def _chosen_deck(self):
        return self.deck_combo.currentData() or deck_manager.get_reference_deck()

    def _on_deck_chosen(self):
        if self.phase != "staged":
            return
        self.deck = self._chosen_deck()

    # -- staging --------------------------------------------------------------------------

    def _pool(self):
        cards = list(self.deck.get_all_cards()) if self.deck else []
        # A card with no art can't be drawn face-up, so it isn't in the draw
        cards = [card for card in cards if card.get("image") and os.path.exists(card["image"])]
        size = os.environ.get("TAROT_SPIKE_DECK_SIZE")
        if size:
            cards = cards[: int(size)]
        return cards

    def _card_size(self):
        cards = self._pool()
        for card in cards:
            item = self.make_card_item(card, self.deck, False)
            if item is not None:
                return item.pixmap().size()
        slot = self._slots[0] if self._slots else None
        return slot.pixmap().size() if slot else None

    def _slot_bounds(self):
        rect = QRectF()
        for slot in self._slots:
            rect = rect.united(slot.sceneBoundingRect())
        return rect

    def _table_rect(self):
        rect = self._slot_bounds()
        pad = max(rect.width(), rect.height()) * 0.05
        return rect.adjusted(-pad, -pad, pad, pad)

    def _stage_significator(self):
        card_id = os.environ.get("TAROT_SPIKE_SIGNIFICATOR")
        if not card_id or not self._slots or self.deck is None:
            return
        card = self.deck.get_card_by_id(card_id)
        if card is None:
            logger.warning(f"reading spike: no card {card_id} in {self.deck.get_name()}")
            return
        slot = self._slots[0]
        item = CanvasTab.add_specific_card(self, card, self.deck, False, _centre(slot))
        if item is not None:
            item.set_orient(slot.orient)
            item.setSelected(False)

    def _filled_by_hand(self):
        """{slot: card item} for face-up cards lying on a slot when Deal is pressed"""
        filled = {}
        for card in self.cards():
            if isinstance(card, SlotItem | ReadingCard):
                continue
            centre = _centre(card)
            for slot in self._slots:
                if slot not in filled and slot.sceneBoundingRect().contains(centre):
                    filled[slot] = card
                    break
        return filled

    # -- dealing --------------------------------------------------------------------------

    def _level(self):
        return self.motion_level

    def deal(self):
        if self.phase != "staged" or self.deck is None:
            return
        size = self._card_size()
        if size is None:
            return
        self._back = back_pixmap(self.deck, size)
        self.refresh_motion_settings()
        level = self._level()
        self.phase = "dealing"
        self.deal_button.setEnabled(False)
        self.deck_combo.setEnabled(False)
        # Disabling Deal would hand the focus to another pane control; the keys that turn are the canvas's
        self.view.setFocus(Qt.FocusReason.OtherFocusReason)
        self.scene.clearSelection()

        by_hand = self._filled_by_hand()
        for slot, item in by_hand.items():
            item.setPos(_centre(slot) - item.boundingRect().center())
            item.set_orient(slot.orient)
        taken = {item.card_data.get("id") for item in by_hand.values()}
        for slot, item in by_hand.items():
            placement = self._placement_at(slot)
            placement.fill(item)
            placement.sync_slot(landed=True)

        pool = [card for card in self._pool() if card.get("id") not in taken]
        open_slots = [slot for slot in self._slots if slot not in by_hand]
        if self._deal_order == "z":
            open_slots.sort(key=lambda slot: slot.zValue())
        count = min(len(open_slots), len(pool))
        if count < len(open_slots):
            logger.info(
                f"reading spike: short deal, {len(pool)} cards for {len(open_slots)} positions"
            )
        drawn = random.sample(pool, count)
        forced = os.environ.get("TAROT_SPIKE_REVERSED")

        dealt = []
        for slot, card in zip(open_slots, drawn, strict=False):
            reversed = {"all": True, "none": False}.get(forced, random.choice([True, False]))
            item = self.make_card_item(card, self.deck, reversed)
            if item is None:
                continue
            reading = ReadingCard(item._base, card, self, self.deck, reversed, self._back)
            reading._art_path = item._art_path
            reading._top_level = item._top_level
            reading.slot = slot
            dealt.append(reading)
            self._placement_at(slot).fill(reading)
            logger.debug(
                f"reading spike: {slot.number} {slot.label!r} <- {card.get('name')}"
                f"{' (reversed)' if reversed else ''}"
            )

        number = {id(slot): slot.number for slot in self._slots}
        if self._turn_order == "deal":
            self._turn_queue = list(dealt)
        else:
            self._turn_queue = sorted(dealt, key=lambda card: number[id(card.slot)])
        self._dealt = dealt
        self._candle_target = 1.0 if dealt else 0.0

        if level == "Off":
            for card in dealt:
                self._land(card, instant=True)
            self._candle = self._candle_target
            self._finish_deal()
            self.view.viewport().update()
            return

        # From just below the view's bottom edge, toward the reader
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self._deal_from = QPointF(visible.center().x(), visible.bottom() + size.height() * 0.7)
        start = 0.0
        flight = FLIGHT_S if level == "Full" else 2 * TICK_MS / 1000.0
        self._flights = [
            {"card": card, "start": start + i * DEAL_GAP_S, "duration": flight, "from": None}
            for i, card in enumerate(dealt)
        ]
        self._deal_started = None
        self._clock(True)

    def _land(self, card, instant):
        slot = card.slot
        if card.scene() is None:
            self.scene.addItem(card)
        card.setPos(_centre(slot) - card.boundingRect().center())
        card.motion.orient = slot.orient % 360
        card.motion.orient_lag = 0.0
        card.setZValue(CARD_Z + slot.zValue())
        card._apply_motion()
        if not instant:
            card.place_and_settle()
        self._landed.add(card)
        card.placement.sync_slot(landed=True)
        self.refresh_rows()

    def _finish_deal(self):
        self.phase = "dealt" if self._turn_queue else "read"
        self._top_z = max([self._top_z] + [c.zValue() for c in self._dealt])
        self.turn_all_button.setEnabled(bool(self._turn_queue))
        self._sync_next()
        self.halo.attach(self._turn_queue[0] if self._turn_queue else None, fade=self._animates())

    def _animates(self):
        return self._level() != "Off"

    def _step_flights(self, t, dt):
        if self._deal_started is None:
            self._deal_started = t
        elapsed = t - self._deal_started
        remaining = []
        for flight in self._flights:
            card = flight["card"]
            if elapsed < flight["start"]:
                remaining.append(flight)
                continue
            if flight["from"] is None:
                spread = card.boundingRect().width() * 0.15
                flight["from"] = self._deal_from + QPointF(random.uniform(-spread, spread), 0.0)
                self.scene.addItem(card)
                card.setZValue(FLIGHT_Z + len(remaining))
            u = min(1.0, (elapsed - flight["start"]) / flight["duration"])
            if u >= 1.0:
                self._land(card, instant=False)
                continue
            e = _ease_out(u)
            a = flight["from"]
            b = _centre(card.slot)
            delta = b - a
            length = math.hypot(delta.x(), delta.y()) or 1.0
            # A gentle arc: bow to the flight's left by a tenth of its length
            bow = 0.12 * length * math.sin(math.pi * e)
            normal = QPointF(-delta.y() / length, delta.x() / length)
            centre = a + delta * e + normal * bow
            card.setPos(centre - card.boundingRect().center())
            target = card.slot.orient % 360
            turn = (target + 180.0) % 360.0 - 180.0
            card.motion.orient = (turn * e) % 360
            card._lift.snap(1.0 + 0.08 * math.sin(math.pi * e))
            card.motion.lift = card._lift.value
            card._apply_motion()
            remaining.append(flight)
        self._flights = remaining
        if not remaining:
            self._deal_started = None
            self._finish_deal()

    # -- turning --------------------------------------------------------------------------

    def _sync_next(self):
        following = self._turn_queue[0] if self._turn_queue else None
        for card in self._dealt:
            card.set_next(card is following and self.phase == "dealt")
        if following is not None and self.phase == "dealt":
            following.setZValue(NEXT_Z)
        self.refresh_rows()
        if following is not None and self.phase == "dealt":
            self.pane.list_view.scrollTo(self.positions.index_of(following.slot))

    # -- the pane's rows ------------------------------------------------------------------

    def card_in(self, slot):
        """The card on slot: dealt, or put there by hand before the deal"""
        if self.phase == "staged":
            return self._filled_by_hand().get(slot)
        card = self._placement_at(slot).card
        # A dealt card shows in its row once it has landed
        if self.phase == "dealing" and card in self._dealt and card not in self._landed:
            return None
        return card

    def is_next_slot(self, slot):
        return self.phase == "dealt" and bool(self._turn_queue) and self._turn_queue[0].slot is slot

    def refresh_rows(self):
        if hasattr(self, "rows"):
            selected = self.pane.list_view.selectionModel().selectedRows()
            open_rows = {index.row() for index in selected}
            following = self._turn_queue[0] if self._turn_queue else None
            if following is not None and self.phase == "dealt":
                open_rows.add(self._slots.index(following.slot))
            self.rows.set_open_rows(open_rows)
        self.pane.list_view.viewport().update()

    def has_next(self):
        return bool(self._turn_queue)

    def card_clicked(self, card):
        if self.phase == "dealt" and self._turn_queue and card is self._turn_queue[0]:
            self.turn_next()

    def turn_next(self):
        if not self._turn_queue:
            return
        card = self._turn_queue.pop(0)
        following = self._turn_queue[0] if self._turn_queue else None
        animate = self._animates()
        # Above the next card while it turns, then back to its own depth
        card.setZValue(TURNING_Z)
        self._sync_next()
        self.halo.flare(following, animate)
        if not self._turn_queue:
            self.turn_all_button.setEnabled(False)
            self._candle_target = 0.0
            if not animate:
                self._candle = 0.0
                self.view.viewport().update()
        card.begin_turn(animate)

    def turn_all(self):
        if not self._turn_queue:
            return
        if not self._animates():
            while self._turn_queue:
                self.turn_next()
            return
        self.turn_next()
        self._turn_all_at = self._now + TURN_ALL_GAP_S

    def card_turned(self, card):
        card.setZValue(CARD_Z + card.slot.zValue())
        self.refresh_rows()
        if not self._turn_queue and not any(c.is_turning() for c in self._dealt if c is not card):
            self.phase = "read"
            self.layout_changed.emit()

    # -- the caption, over everything ------------------------------------------------------

    def set_caption_opacity(self, opacity):
        if opacity != self.caption.opacity():
            self.caption.setOpacity(opacity)
            self.update_caption()

    def update_caption(self):
        self.view.viewport().update()

    def _paint_caption(self, painter, rect):
        caption = self.caption
        if not caption.isVisible() or caption.opacity() <= 0.0:
            return
        caption.place()
        anchor = QPointF(self.view.mapFromScene(caption.pos()))
        box = caption.boundingRect()
        viewport = self.view.viewport().rect()
        # No room below the card: above it instead
        if anchor.y() + box.bottom() > viewport.height():
            top = self.view.mapFromScene(caption.slot_rect().topLeft()).y()
            card_top = min(top, self.view.mapFromScene(caption.slot_rect().topRight()).y())
            anchor.setY(card_top - box.bottom())
        # And never off the view's sides
        margin = CAPTION_GAP_PX
        anchor.setX(
            max(margin - box.left(), min(viewport.width() - margin - box.right(), anchor.x()))
        )
        painter.save()
        # In viewport pixels, as the item drew itself with ItemIgnoresTransformations
        painter.resetTransform()
        painter.translate(anchor)
        painter.setOpacity(caption.opacity())
        caption.paint(painter, None)
        painter.restore()

    # -- the candle -----------------------------------------------------------------------

    def candle_level(self):
        return self._candle

    def _dim(self):
        ground = self._ground
        if ground.lightness() > 128:
            return ground.darker(300)
        return QColor(10, 7, 5)

    def _paint_candle(self, painter, rect):
        level = self._candle
        if level <= 0.0:
            return
        table = self._table_rect()
        if table.isNull():
            return
        centre = table.center()
        rx = max(1.0, table.width() / 2.0 * CANDLE_REACH)
        ry = max(1.0, table.height() / 2.0 * CANDLE_REACH)
        dim = self._dim()
        alpha = CANDLE_ALPHA * level
        gradient = QRadialGradient(QPointF(0, 0), 1.0)
        for stop, share in ((0.0, 0.0), (0.55, 0.12), (0.8, 0.55), (1.0, 1.0)):
            colour = QColor(dim)
            colour.setAlphaF(alpha * share)
            gradient.setColorAt(stop, colour)
        painter.save()
        painter.translate(centre)
        painter.scale(rx, ry)
        local = QRectF(
            (rect.x() - centre.x()) / rx,
            (rect.y() - centre.y()) / ry,
            rect.width() / rx,
            rect.height() / ry,
        )
        painter.fillRect(local, QBrush(gradient))
        painter.restore()

    # -- the clock ------------------------------------------------------------------------

    def _clock(self, on):
        if on and not self._clock_on and self._animates():
            self.motion_clock.subscribe(self._reading_tick)
            self._clock_on = True
        elif not on and self._clock_on:
            self.motion_clock.unsubscribe(self._reading_tick)
            self._clock_on = False

    def _reading_tick(self, t, dt):
        self._now = t
        full = self._level() == "Full"
        if self.phase == "dealing":
            self._step_flights(t, dt)
        if self._turn_all_at is not None and t >= self._turn_all_at:
            self.turn_next()
            self._turn_all_at = t + TURN_ALL_GAP_S if self._turn_queue else None
        self.halo.advance(t, dt, full)

        if self._candle != self._candle_target:
            step = dt / (CANDLE_IN_S if self._candle_target > self._candle else CANDLE_OUT_S)
            if self._candle < self._candle_target:
                self._candle = min(self._candle_target, self._candle + step)
            else:
                self._candle = max(self._candle_target, self._candle - step)
            self.view.viewport().update()

        idle = (
            self.phase == "read" and self.halo.card is None and self._candle == self._candle_target
        )
        if idle:
            self._clock(False)

    def showEvent(self, event):
        super().showEvent(event)
        if self.phase in ("dealing", "dealt") or self._candle != self._candle_target:
            self._clock(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._clock(False)

    def settle_motion(self):
        super().settle_motion()
        if getattr(self, "phase", None) == "dealing":
            for flight in self._flights:
                self._land(flight["card"], instant=True)
            self._flights = []
            self._finish_deal()
