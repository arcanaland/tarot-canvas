"""A reading's phases and positions: one Placement per position, and the socket drawn while it is
empty."""

from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.slot_item import SlotItem, render_slot


class Phase(Enum):
    """Where a reading is. Nothing goes back: a turned card can't be un-turned"""

    # The spread's positions are sockets, and the deck and Reversals can be chosen
    STAGED = "staged"
    # The cards are on the table, some still face-down
    DEALT = "dealt"
    # Every dealt card is face-up, and the canvas is an ordinary one again
    READ = "read"


# An empty position: a socket in the house back's plum and brass, dashed, with no icon, so it can't
# be taken for a card already dealt face-down. Its plum is laid over the ground ahead of time, so it
# looks see-through but covers what lies under it, as a crossing card does
SOCKET_PLUM = QColor(58, 36, 48)
SOCKET_PLUM_SHARE = 120 / 255
SOCKET_EDGE = QColor(170, 138, 98)
SOCKET_INK = QColor(214, 180, 132)


def socket_fill(ground):
    """The plum at its share over ground, made opaque"""
    ground = QColor(ground)
    a = SOCKET_PLUM_SHARE
    return QColor.fromRgbF(
        a * SOCKET_PLUM.redF() + (1 - a) * ground.redF(),
        a * SOCKET_PLUM.greenF() + (1 - a) * ground.greenF(),
        a * SOCKET_PLUM.blueF() + (1 - a) * ground.blueF(),
    )


def render_socket(slot, scale, ground):
    """slot's face as a socket over ground, its text turned back by the nearest quarter so it reads
    upright, across a crossing slot"""
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
    """A position of a reading, drawn as a socket while it is empty. It is read, not designed: it
    can't be picked, moved or selected, and lies flat in the table, so it casts no shadow"""

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
        return getattr(self.parent_tab, "ground", None) or QColor(Qt.GlobalColor.darkGray)

    def _render(self, scale):
        return render_socket(self, scale, self._ground())

    def redraw(self):
        """Draw again, for a new ground or a new turn"""
        self._redraw()

    def set_orient(self, degrees):
        super().set_orient(degrees)
        # Its text is turned back by its orient
        self._redraw()


class Placement:
    """One position of the spread and the card that fills it.

    The socket on the canvas, the row in the pane and the card are three views of this. The socket
    is drawn only while nothing fills the position; the card carries the position wherever it is
    moved, and selecting the card or the row selects the other
    """

    def __init__(self, slot):
        self.slot = slot
        self.card = None
        # Filled by hand before the deal, so it was never face-down
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
        # Its shadow is an item of its own, and would stay on the table
        self.slot.shadow.setVisible(False)
