"""The room dims like a candle-lit table while any card is face-down"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QRadialGradient
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.motion import Pace
from tarot_canvas.ui.canvas.placement import DIM_IN_S, DIM_LIFT_S

CANDLE_ALPHA = 0.8
# Of the table's half-size, where the dark is whole
CANDLE_REACH = 1.42
# (share of the reach, share of the dark): clear over the table, whole at the reach
CANDLE_STOPS = ((0.0, 0.0), (0.55, 0.12), (0.8, 0.55), (1.0, 1.0))
# The dim is the ground at a third of its value: a light ground stays a tone of itself
DIM_DARKER = 300

# Of the haloed card's longer side
WARM_PATCH_REACH = 1.25
WARM_PATCH_ALPHA = 60
WARM_PATCH_INNER = QColor(255, 150, 60)
WARM_PATCH_OUTER = QColor(255, 120, 40)


def dim_tone(ground):
    return QColor(ground).darker(DIM_DARKER)


class Candle:
    """A foreground hook darkening the view outside table_rect() toward ground()'s dim tone"""

    def __init__(self, view, table_rect, ground):
        self._view = view
        self._table_rect = table_rect
        self._ground = ground
        self._pace = Pace(0.0)

    @property
    def level(self):
        return self._pace.value

    def set_lit(self, lit, animate):
        """Dim the room (lit: only the candle lights it), or lift the dim"""
        if lit:
            self._pace.set_target(1.0, DIM_IN_S)
        else:
            self._pace.set_target(0.0, DIM_LIFT_S)
        if not animate:
            self._pace.snap()
        self._view.viewport().update()

    def is_still(self):
        return self._pace.value == self._pace.target

    def advance(self, dt):
        if self.is_still():
            return
        self._pace.advance(dt)
        self._view.viewport().update()

    def snap(self):
        if not self.is_still():
            self._pace.snap()
            self._view.viewport().update()

    def __call__(self, painter, rect):
        level = self._pace.value
        if level <= 0.0:
            return
        table = self._table_rect()
        if table.isNull():
            return
        centre = table.center()
        rx = max(1.0, table.width() / 2.0 * CANDLE_REACH)
        ry = max(1.0, table.height() / 2.0 * CANDLE_REACH)
        dim = dim_tone(self._ground())
        alpha = CANDLE_ALPHA * level
        gradient = QRadialGradient(QPointF(0, 0), 1.0)
        for stop, share in CANDLE_STOPS:
            colour = QColor(dim)
            colour.setAlphaF(alpha * share)
            gradient.setColorAt(stop, colour)
        painter.save()
        # A unit circle stretched to the table's ellipse
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


class WarmPatch(QGraphicsItem):
    """The candle's warm light thrown on the table under one card"""

    frames_home = False

    def __init__(self):
        super().__init__()
        self.card = None
        self.alpha = 0
        self._reach = 0.0
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    def boundingRect(self):
        r = self._reach
        return QRectF(-r, -r, 2 * r, 2 * r)

    def follow(self, card):
        """Lie under card, or go with None"""
        self.card = card
        if card is None:
            self.setVisible(False)
            return
        rect = card.boundingRect()
        reach = max(rect.width(), rect.height()) * WARM_PATCH_REACH
        if reach != self._reach:
            self.prepareGeometryChange()
            self._reach = reach
        self.setPos(card.pos() + rect.center())
        # Over the card's shadow, under its halo
        self.setZValue(card.zValue() - 0.3)
        self.setVisible(True)

    def set_strength(self, strength):
        """strength 0 to a little over 1: the halo's glow times the candle's level"""
        alpha = min(255, round(WARM_PATCH_ALPHA * max(0.0, strength)))
        if alpha != self.alpha:
            self.alpha = alpha
            self.update()

    def paint(self, painter, option, widget=None):
        if self.alpha <= 0:
            return
        reach = self._reach
        gradient = QRadialGradient(QPointF(0, 0), reach)
        inner = QColor(WARM_PATCH_INNER)
        inner.setAlpha(self.alpha)
        middle = QColor(WARM_PATCH_OUTER)
        middle.setAlpha(self.alpha // 3)
        outer = QColor(WARM_PATCH_OUTER)
        outer.setAlpha(0)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(0.5, middle)
        gradient.setColorAt(1.0, outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), reach, reach)
