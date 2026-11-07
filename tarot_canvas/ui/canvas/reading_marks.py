"""What a reading paints over its canvas, in viewport pixels: each filled position's number at its
card's corner, and the next card's position under it. Foreground painters, so they stay upright
and at screen size at any zoom or turn, on raster and GL alike."""

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, gilt_for_ground

CAPTION_WIDTH_PX = 300
CAPTION_GAP_PX = 10
CAPTION_PAD_PX = 8
CAPTION_FILL = QColor(20, 14, 10, 200)
CAPTION_TEXT = QColor(255, 240, 220)
CAPTION_MEANING = QColor(225, 205, 185)
MEANING_LINES = 2
# The ink on a lit badge's gilt
BADGE_INK = QColor(30, 18, 8)
# A position's badge on its card: this far in from the card's corner, as a share of the badge
BADGE_INSET = 0.35
BADGE_RING_PX = 1.5


def next_gilt(palette):
    """The next card's mark on a widget: the canvas's selection gilt, for the window's ground"""
    return gilt_for_ground(palette.window().color())


def paint_badge(painter, circle, number, font, lit):
    """A position's number in a disc: gilt for the next card, else dark with a gilt ring"""
    gilt = QColor(GILT_ON_DARK)
    painter.setPen(Qt.PenStyle.NoPen if lit else QPen(gilt, BADGE_RING_PX))
    painter.setBrush(gilt if lit else CAPTION_FILL)
    painter.drawEllipse(circle)
    painter.setFont(font)
    painter.setPen(BADGE_INK if lit else gilt)
    painter.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), str(number))


def _viewport_painting(painter):
    painter.save()
    painter.resetTransform()
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)


class Badges:
    """Each filled position's number at its card's bounding-rect corner, face-down included: the
    layout reads before the turn too. Inside the card, so a moved card's repaint takes its old
    badge with it"""

    def __init__(self, view, marks):
        """marks() gives (card, number, lit) for every badge to paint"""
        self.view = view
        self._marks = marks
        self.font = typography.font(typography.Role.SMALL)
        self.font.setBold(True)

    def __call__(self, painter, rect):
        marks = self._marks()
        if not marks:
            return
        side = QFontMetricsF(self.font).height() + 4
        inset = side * BADGE_INSET
        _viewport_painting(painter)
        for card, number, lit in marks:
            corner = self.view.mapFromScene(card.sceneBoundingRect()).boundingRect().topLeft()
            circle = QRectF(corner.x() + inset, corner.y() + inset, side, side)
            paint_badge(painter, circle, number, self.font, lit)
        painter.restore()


class Caption:
    """The next card's position under it, at screen size: its number, label and meaning in the
    spread's own words. Above the card when there is no room below, and never off the view's sides"""

    def __init__(self, view):
        self.view = view
        self.slot = None
        self.opacity = 1.0
        self._rect = QRectF()
        self._lines = 0
        self._title_font = typography.font(typography.Role.BODY)
        self._title_font.setBold(True)
        self._small_font = typography.font(typography.Role.SMALL)

    def show_for(self, slot):
        """Sit under slot, the next card's position, or hide with None"""
        self.slot = slot
        if slot is not None:
            self._measure(slot)
        self.view.viewport().update()

    def _meaning(self):
        return " ".join(self.slot.meaning.split())

    def _measure(self, slot):
        title = QFontMetricsF(self._title_font)
        small = QFontMetricsF(self._small_font)
        badge = title.height()
        text_width = CAPTION_WIDTH_PX - 3 * CAPTION_PAD_PX - badge
        label_width = min(text_width, title.horizontalAdvance(slot.label))
        meaning = self._meaning()
        meaning_width = min(text_width, small.horizontalAdvance(meaning)) if meaning else 0.0
        lines = 0
        if meaning:
            lines = min(MEANING_LINES, math.ceil(small.horizontalAdvance(meaning) / text_width))
        width = 3 * CAPTION_PAD_PX + badge + max(label_width, meaning_width)
        height = 2 * CAPTION_PAD_PX + title.height() + lines * small.lineSpacing()
        self._rect = QRectF(-width / 2.0, CAPTION_GAP_PX, width, height)
        self._lines = lines

    def rect(self):
        """Where it is painted now, in viewport px; null while hidden"""
        if self.slot is None or self.opacity <= 0.0:
            return QRectF()
        return self._rect.translated(self._anchor())

    def _anchor(self):
        """The point under the slot's middle it hangs from, moved to stay in the view"""
        slot_rect = self.view.mapFromScene(self.slot.sceneBoundingRect()).boundingRect()
        anchor = QPointF(slot_rect.center().x(), slot_rect.bottom())
        box = self._rect
        viewport = self.view.viewport().rect()
        # No room below the card: above it instead
        if anchor.y() + box.bottom() > viewport.height():
            anchor.setY(slot_rect.top() - box.bottom())
        margin = CAPTION_GAP_PX
        anchor.setX(
            max(margin - box.left(), min(viewport.width() - margin - box.right(), anchor.x()))
        )
        return anchor

    def __call__(self, painter, rect):
        if self.slot is None or self.opacity <= 0.0:
            return
        _viewport_painting(painter)
        painter.translate(self._anchor())
        painter.setOpacity(self.opacity)
        self._paint(painter)
        painter.restore()

    def _paint(self, painter):
        slot = self.slot
        rect = self._rect
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(CAPTION_FILL)
        painter.drawRoundedRect(rect, CAPTION_PAD_PX, CAPTION_PAD_PX)

        title = QFontMetricsF(self._title_font)
        badge = title.height()
        top = rect.top() + CAPTION_PAD_PX
        circle = QRectF(rect.left() + CAPTION_PAD_PX, top, badge, badge)
        paint_badge(painter, circle, slot.number, self._title_font, lit=True)

        left = circle.right() + CAPTION_PAD_PX
        width = rect.right() - CAPTION_PAD_PX - left
        painter.setPen(CAPTION_TEXT)
        painter.drawText(
            QRectF(left, top, width, title.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title.elidedText(slot.label, Qt.TextElideMode.ElideRight, width),
        )
        if not self._lines:
            return
        small = QFontMetricsF(self._small_font)
        meaning = self._meaning()
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
