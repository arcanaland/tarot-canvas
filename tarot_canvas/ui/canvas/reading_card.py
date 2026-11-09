"""A card we're dealing that is flown in, face-down, then an ordinary canvas card."""

import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.backs import HOUSE_EDGE_PX, HOUSE_RADIUS
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.motion import TICK_MS, MotionChannels

TURN_S = 0.5
# How far a card lifts as it is turned over
TURN_LIFT = 1.10
# A face-down card's colour on the tab icon
FACE_DOWN_MARK = QColor(110, 96, 90)

# The halo's light caught by a face-down card's edge, drawn with Plus
RIM_RGB = (255, 170, 70)
RIM_ALPHA = 200
RIM_GLOW_PX = 10.0
RIM_GLOW_ALPHA = 70
# The light at which the edge's alpha is whole: the rim is baked at it and drawn at a share
RIM_FULL = 255 / RIM_ALPHA
# A change in the rim's light smaller than this is not repainted
RIM_STEP = 1.0 / 255.0


@lru_cache(maxsize=8)
def rim_pixmap(width, height, dpr, house):
    """The rim at a light of RIM_FULL, for a back of width by height device px"""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)
    rect = QRectF(0, 0, width / dpr, height / dpr)
    radius = rect.width() * HOUSE_RADIUS if house else 0.0
    inset = HOUSE_EDGE_PX / 2.0
    edge = rect.adjusted(inset, inset, -inset, -inset)
    r, g, b = RIM_RGB
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # A soft glow just inside the edge, then the edge itself
    painter.setPen(QPen(QColor(r, g, b, round(RIM_GLOW_ALPHA * RIM_FULL)), RIM_GLOW_PX))
    painter.drawRoundedRect(edge, radius, radius)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setPen(QPen(QColor(r, g, b, 255), HOUSE_EDGE_PX))
    painter.drawRoundedRect(edge, radius, radius)
    painter.end()
    return pixmap


def is_face_down(item):
    """Whether item is a dealt card not yet turned"""
    return isinstance(item, ReadingCard) and item.face_down


# Seconds between cards leaving, and each one's flight
DEAL_GAP_S = 0.12
FLIGHT_S = 0.42
# Reactive motion: a flight just long enough to be seen to land
REACTIVE_FLIGHT_S = 2 * TICK_MS / 1000.0
# A flight bows to its left by this share of its length, and lifts by this much at its height
FLIGHT_BOW = 0.12
FLIGHT_LIFT = 0.08
# Cards leave from this far below the view's bottom edge, in card heights, and this far either side
# of its middle, in card widths
DEAL_FROM_BELOW = 0.7
DEAL_FROM_SPREAD = 0.15


def ease_in_out(u):
    return u * u * (3.0 - 2.0 * u)


def ease_out(u):
    return 1.0 - (1.0 - u) ** 3


@dataclass
class ReadingMotion(MotionChannels):
    """MotionChannels plus a turn about the card's own vertical axis"""

    # Degrees through the turn over: 0 to 90 shows the back, -90 to 0 the face
    flip: float = 0.0

    def face_turn(self):
        # A reversed face is drawn turned 180°, so its vertical axis points the other way
        return -self.flip if self.reversed else self.flip

    def at_rest(self):
        return super().at_rest() and self.flip == 0.0

    def snapshot(self):
        return (*super().snapshot(), self.flip)


class ReadingCard(DraggableCardItem):
    """A dealt card."""

    def __init__(self, pixmap, card_data, parent_tab=None, deck=None, reversed=False):
        # we need to draw the back upright until the reveal (otherwise they'll know it's reversed)
        super().__init__(pixmap, card_data, parent_tab, deck=deck, reversed=False)
        self.motion = ReadingMotion()
        self._applied = None
        self._applied_corners = None
        self.drawn_reversed = reversed
        self.face_down = True
        self._turning = None
        # The halo's light on the back's edge, 0 to a little over 1
        self.rim = 0.0
        self._house_back = False
        self.set_interactive(False)
        self._apply_motion()

    def lie_face_down(self, back, house=False):
        """Show back until the turn; house says it is the house back, with its rounded corners"""
        self.setPixmap(back)
        self._house_back = house

    def set_rim(self, light):
        if abs(light - self.rim) < RIM_STEP and (light > 0.0) == (self.rim > 0.0):
            return
        self.rim = light
        if self.face_down:
            self.update()

    def set_interactive(self, interactive):
        flags = QGraphicsItem.GraphicsItemFlag
        self.setFlag(flags.ItemIsMovable, interactive)
        self.setFlag(flags.ItemIsSelectable, interactive)
        self.setAcceptHoverEvents(interactive)
        self.setCursor(Qt.CursorShape.OpenHandCursor if interactive else Qt.CursorShape.ArrowCursor)

    def set_next(self, is_next):
        if not self.face_down:
            return
        self.setAcceptHoverEvents(is_next)
        self.setCursor(Qt.CursorShape.PointingHandCursor if is_next else Qt.CursorShape.ArrowCursor)
        if not is_next:
            self.end_hover()

    def mark_colour(self):
        return FACE_DOWN_MARK if self.face_down else super().mark_colour()

    def set_detail(self, device_scale):
        if not self.face_down:
            super().set_detail(device_scale)

    def is_turning(self):
        return self._turning is not None

    def begin_turn(self, animate):
        """Turn face-up"""
        if not animate:
            self._reveal()
            self.motion.flip = 0.0
            self._apply_motion()
            self._turned()
            return
        self._turning = 0.0
        self._lift.snap(TURN_LIFT)
        self.motion.lift = TURN_LIFT
        self._apply_motion()

    def _reveal(self):
        self.face_down = False
        self.motion.reversed = self.drawn_reversed
        self._wanted_level = 1
        self._show_level(1, self.face_pixmap())
        self.end_hover()
        self.set_interactive(True)
        self._schedule_tab_icon()
        tab = self.parent_tab
        if tab is not None:
            tab.card_revealed(self)

    def _turned(self):
        if self.parent_tab is not None:
            self.parent_tab.card_turned(self)

    def advance_motion(self, t, dt, ambient_gain, view_scale=1.0):
        if self._turning is not None:
            self._turning += dt
            u = min(1.0, self._turning / TURN_S)
            angle = 180.0 * ease_in_out(u)
            # The face replaces the back edge-on
            if angle >= 90.0 and self.face_down:
                self._reveal()
            self.motion.flip = angle if self.face_down else angle - 180.0
            if u >= 1.0:
                self.motion.flip = 0.0
                self._turning = None
                self._turned()
        return super().advance_motion(t, dt, ambient_gain, view_scale)

    def settle_motion(self):
        if self._turning is not None:
            if self.face_down:
                self._reveal()
            self.motion.flip = 0.0
            self._turning = None
            self._turned()
        return super().settle_motion()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.face_down and self.rim > 0.0:
            self._paint_rim(painter)

    def _paint_rim(self, painter):
        back = self.pixmap()
        rim = rim_pixmap(back.width(), back.height(), back.devicePixelRatio(), self._house_back)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setOpacity(min(1.0, self.rim / RIM_FULL))
        painter.drawPixmap(self.offset(), rim)
        painter.restore()

    # -- the pointer: face-down, only a turn ------------------------------------------

    def mousePressEvent(self, event):
        if self.face_down:
            event.accept()
            if event.button() == Qt.MouseButton.LeftButton and self.parent_tab is not None:
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


class Flights:
    """Cards flying in one after another"""

    def __init__(self, scene):
        self._scene = scene
        self._flights = []
        self._started = None
        self._origin = QPointF()

    def is_active(self):
        return bool(self._flights)

    def cards(self):
        """cards not yet landed"""
        return [flight["card"] for flight in self._flights]

    def launch(self, cards, visible, duration, z):
        """Fly all of the cards"""
        height = cards[0][0].boundingRect().height() if cards else 0.0
        self._origin = QPointF(visible.center().x(), visible.bottom() + height * DEAL_FROM_BELOW)
        self._flights = [
            {"card": card, "slot": slot, "start": i * DEAL_GAP_S, "from": None}
            for i, (card, slot) in enumerate(cards)
        ]
        self._duration = duration
        self._z = z
        self._started = None

    def clear(self):
        self._flights = []
        self._started = None

    def advance(self, t):
        """Step each flight to time t. Returns the cards that arrived."""
        if self._started is None:
            self._started = t
        elapsed = t - self._started
        remaining = []
        arrived = []
        for flight in self._flights:
            card = flight["card"]
            if elapsed < flight["start"]:
                remaining.append(flight)
                continue
            if flight["from"] is None:
                spread = card.boundingRect().width() * DEAL_FROM_SPREAD
                flight["from"] = self._origin + QPointF(random.uniform(-spread, spread), 0.0)
                self._scene.addItem(card)
                card.setZValue(self._z + len(remaining))
            u = min(1.0, (elapsed - flight["start"]) / self._duration)
            if u >= 1.0:
                arrived.append(card)
                continue
            self._fly(card, flight["slot"], flight["from"], ease_out(u))
            remaining.append(flight)
        self._flights = remaining
        return arrived

    @staticmethod
    def _fly(card, slot, start, e):
        """card e of the way from start to slot"""
        target = slot.pos() + slot.boundingRect().center()
        delta = target - start
        length = math.hypot(delta.x(), delta.y()) or 1.0
        bow = FLIGHT_BOW * length * math.sin(math.pi * e)
        normal = QPointF(-delta.y() / length, delta.x() / length)
        card.setPos(start + delta * e + normal * bow - card.boundingRect().center())
        turn = (slot.orient % 360 + 180.0) % 360.0 - 180.0
        card.motion.orient = (turn * e) % 360
        card._lift.snap(1.0 + FLIGHT_LIFT * math.sin(math.pi * e))
        card.motion.lift = card._lift.value
        card._apply_motion()
