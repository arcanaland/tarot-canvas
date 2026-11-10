"""Phases and positions for readings"""

from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.slot_item import SlotItem, render_slot


class Phase(Enum):
    """Phases for the reading"""

    # 1: sockets + setup options are unlocked
    STAGED = "staged"
    # 2: cards are dealt and options are locked
    DEALT = "dealt"
    # 3: every card revealed
    READ = "read"


# swirl pace while any card is face-down
FACE_DOWN_GROUND_PACE = 0.2
DIM_IN_S = 0.6
DIM_LIFT_S = 1.0


# Sockets are empty positions
SOCKET_PLUM = QColor(58, 36, 48)
SOCKET_PLUM_SHARE = 120 / 255
SOCKET_EDGE = QColor(170, 138, 98)
SOCKET_INK = QColor(214, 180, 132)


def socket_fill(ground):
    """fill color for the socket"""
    ground = QColor(ground)
    a = SOCKET_PLUM_SHARE
    return QColor.fromRgbF(
        a * SOCKET_PLUM.redF() + (1 - a) * ground.redF(),
        a * SOCKET_PLUM.greenF() + (1 - a) * ground.greenF(),
        a * SOCKET_PLUM.blueF() + (1 - a) * ground.blueF(),
    )


def render_socket(slot, scale, ground):
    turn = round(slot.orient / 90.0) * 90 % 360
    return render_slot(
        slot.number,
        slot.label,
        socket_fill(ground),
        slot._size,
        scale,
        edge=SOCKET_EDGE,
        ink=SOCKET_INK,
        dashed=True,
        text_turn=turn,
    )


class SocketItem(SlotItem):
    """A position of a reading"""

    def __init__(self, number, position_id, parent_tab=None, label="", meaning=""):
        super().__init__(number, position_id, parent_tab, label=label, meaning=meaning)
        flags = QGraphicsItem.GraphicsItemFlag
        self.setFlag(flags.ItemIsMovable, False)
        self.setFlag(flags.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.shadow.setVisible(False)
        self.redraw()

    def _ground(self):
        return getattr(self.parent_tab, "ground_colour", None) or QColor(Qt.GlobalColor.darkGray)

    def _render(self, scale):
        return render_socket(self, scale, self._ground())

    def redraw(self):
        self._redraw()

    def set_orient(self, degrees):
        super().set_orient(degrees)
        # Its text is turned back by its orient
        self._redraw()


class Placement:
    """One position of the spread + the card that slotted in"""

    def __init__(self, slot):
        self.slot = slot
        self.card = None

        # Filled by hand before the deal
        self.by_hand = False

    @property
    def number(self):
        return self.slot.number

    def fill(self, card, by_hand=False):
        self.card = card
        self.by_hand = by_hand

    def sync_slot(self, landed):
        """The socket shows only while no card has landed on it"""
        shown = self.card is None or not landed
        self.slot.setVisible(shown)
        self.slot.shadow.setVisible(False)
