"""A dealt card: flown in, face-down until its turn, then an ordinary canvas card."""

import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.motion import TICK_MS, MotionChannels

TURN_S = 0.5
# How far a card lifts as it is turned over
TURN_LIFT = 1.10
# A face-down card's colour on the tab icon: no suit's
FACE_DOWN_MARK = QColor(110, 96, 90)


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
    """A dealt card. Face-down it shows its deck's back and gives nothing of its face away: not its
    reversal, its suit's colour, its art at a sharper level, its menu or its card view. It answers
    the pointer only when it is the next to turn, and then only to be turned"""

    def __init__(self, pixmap, card_data, parent_tab=None, deck=None, reversed=False):
        # Drawn upright until the turn, or a reversed back would tell
        super().__init__(pixmap, card_data, parent_tab, deck=deck, reversed=False)
        self.motion = ReadingMotion()
        self._applied = None
        self._applied_corners = None
        self.drawn_reversed = reversed
        self.face_down = True
        self._turning = None
        self.set_interactive(False)
        self._apply_motion()

    def lie_face_down(self, back):
        """Show back, a pixmap the size of the face, until the turn"""
        self.setPixmap(back)

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
        return FACE_DOWN_MARK if self.face_down else super().mark_colour()

    def set_detail(self, device_scale):
        # A sharper level is the face's art
        if not self.face_down:
            super().set_detail(device_scale)

    def is_turning(self):
        return self._turning is not None

    def begin_turn(self, animate):
        """Turn face-up: over TURN_S, lifting, or at once"""
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
    """Cards flying in one after another, from just below the view's bottom edge, where the reader
    sits, on a gentle arc to their positions, turning to each one's angle as they go"""

    def __init__(self, scene):
        self._scene = scene
        self._flights = []
        self._started = None
        self._origin = QPointF()

    def is_active(self):
        return bool(self._flights)

    def cards(self):
        """Those not yet landed, in the order they leave"""
        return [flight["card"] for flight in self._flights]

    def launch(self, cards, visible, duration, z):
        """Fly each of cards, as (card, its slot), leaving the bottom of visible, a scene rect.
        In flight they lie at z and up"""
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
        """Step each flight to time t; return the cards that arrived"""
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
