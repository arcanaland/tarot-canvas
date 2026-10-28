import math
from collections import namedtuple
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QIconEngine,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)

from tarot_canvas.ui.canvas.ground import GRADIENT_STOPS
from tarot_canvas.ui.card_colours import CARD_COLOURS, card_colour_key

# Unit-square coordinates: x, y is the mark's centre
Mark = namedtuple("Mark", "x y w h angle colour_key z")

SNAP = 32


@dataclass(frozen=True)
class IconStyle:
    rounding: float  # of a mark's short side
    inset: float  # of the icon, kept clear inside the ground
    max_fill: float  # cap on any mark's longer side, of the area inside the inset
    min_mark_px: float  # device px
    ground_radius: float  # of the icon
    ground_rim: float  # alpha, 0 for none
    mark_rim: float  # alpha, 0 for none
    ground: bool = True


MINIMAP = IconStyle(
    rounding=0.2,
    inset=0.12,
    max_fill=0.6,
    min_mark_px=2.0,
    ground_radius=0.22,
    ground_rim=0.0,
    mark_rim=0.6,
)


def card_marks(cards):
    """Each card's untransformed rect in scene units as (x, y, w, h, angle, colour_key, z)"""
    raw = []
    for card in cards:
        rect = card.boundingRect()
        pos = card.pos()
        raw.append(
            (
                pos.x() + rect.x(),
                pos.y() + rect.y(),
                rect.width(),
                rect.height(),
                card.motion.orient,
                card_colour_key(card.card_data),
                card.zValue(),
            )
        )
    return tuple(raw)


def layout_marks(raw, max_fill=1.0):
    """Fit raw rects into the unit square, keeping the spread's aspect, in ascending z"""
    if not raw:
        return ()
    centres = [(x + w / 2, y + h / 2) for x, y, w, h, *_ in raw]
    longest = max(max(w, h) for _, _, w, h, *_ in raw)
    xs = [cx for cx, _ in centres]
    ys = [cy for _, cy in centres]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) + longest
    scale = min(1.0 / span, max_fill / longest)
    mid_x = (max(xs) + min(xs)) / 2
    mid_y = (max(ys) + min(ys)) / 2
    marks = [
        Mark(
            0.5 + (cx - mid_x) * scale,
            0.5 + (cy - mid_y) * scale,
            w * scale,
            h * scale,
            angle,
            colour_key,
            z,
        )
        for (cx, cy), (_, _, w, h, angle, colour_key, z) in zip(centres, raw, strict=True)
    ]
    return tuple(sorted(marks, key=lambda mark: mark.z))


def snapped(marks):
    """Marks on a 1/SNAP grid with whole-degree angles and z as paint order"""
    return tuple(
        Mark(
            round(m.x * SNAP) / SNAP,
            round(m.y * SNAP) / SNAP,
            round(m.w * SNAP) / SNAP,
            round(m.h * SNAP) / SNAP,
            round(m.angle) % 360,
            m.colour_key,
            i,
        )
        for i, m in enumerate(marks)
    )


def render_spread(marks, style, side):
    """A transparent side x side device-pixel image of marks"""
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if style.ground:
        _paint_ground(painter, side, style)

    inset = side * style.inset
    area = side - 2 * inset
    rim = QColor(GRADIENT_STOPS[-1][1])
    rim.setAlphaF(style.mark_rim)
    for mark in marks:
        w = max(mark.w * area, style.min_mark_px)
        h = max(mark.h * area, style.min_mark_px)
        radius = style.rounding * min(w, h)
        painter.save()
        painter.translate(inset + mark.x * area, inset + mark.y * area)
        painter.rotate(mark.angle)
        painter.setBrush(QColor(CARD_COLOURS[mark.colour_key]))
        painter.setPen(QPen(rim, 1.0) if style.mark_rim else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), radius, radius)
        painter.restore()

    painter.end()
    return image


def _paint_ground(painter, side, style):
    gradient = QRadialGradient(QPointF(side / 2, side / 2), side * math.sqrt(2) / 2)
    gradient.setStops(GRADIENT_STOPS)
    painter.setBrush(gradient)
    radius = side * style.ground_radius
    if style.ground_rim:
        rim = QGuiApplication.palette().text().color()
        rim.setAlphaF(style.ground_rim)
        painter.setPen(QPen(rim, 1.0))
        painter.drawRoundedRect(QRectF(0.5, 0.5, side - 1, side - 1), radius, radius)
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, side, side), radius, radius)


class SpreadIconEngine(QIconEngine):
    """A spread's marks, painted at whatever size is asked for"""

    def __init__(self, marks, style):
        super().__init__()
        self._marks = marks
        self._style = style

    def paint(self, painter, rect, mode, state):
        device = painter.device()
        dpr = device.devicePixelRatioF() if device is not None else 1.0
        side = min(rect.width(), rect.height())
        target = QRect(0, 0, side, side)
        target.moveCenter(rect.center())
        painter.drawImage(target, render_spread(self._marks, self._style, round(side * dpr)))

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        side = min(size.width(), size.height())
        image = render_spread(self._marks, self._style, round(side * scale))
        image.setDevicePixelRatio(scale)
        return QPixmap.fromImage(image)

    def clone(self):
        return SpreadIconEngine(self._marks, self._style)


def spread_icon(marks, style=MINIMAP):
    return QIcon(SpreadIconEngine(marks, style))
