"""Guides that appear to snap with cards on the canvas"""

import math
from dataclasses import dataclass
from itertools import combinations, pairwise

from PyQt6.QtCore import QLineF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsItem

from tarot_canvas.ui.canvas.selection import (
    GILT_ON_DARK,
    LIGHT_GROUND_LUMINANCE,
    ground_luminance,
)

# How close, on screen, a card has to come before it is pulled onto a target
SNAP_RADIUS_PX = 8.0

# Half the length of the end ticks on an equal-gap guide, on screen
GUIDE_TICK_PX = 4.0

# The line, and the band of the opposite tone under it that keeps it legible over card art
GUIDE_CORE_PX = 1.5
GUIDE_HALO_PX = 3.5
GUIDE_HALO_ALPHA = 0.4

# A line guide is dashed - a gap is solid
GUIDE_DASH_PX = 4.0
GUIDE_SPACE_PX = 3.0

# Above every card, its shadow and its marks
GUIDE_Z = 1e12

# Lower wins
CENTRE, EQUAL_GAP, EDGE, MIDPOINT = range(4)


@dataclass(frozen=True)
class Guide:
    """A line segment in scene coordinates, with end ticks if it measures a gap."""

    x1: float
    y1: float
    x2: float
    y2: float
    ticks: bool = False

    def swapped(self):
        return Guide(self.y1, self.x1, self.y2, self.x2, self.ticks)


@dataclass(frozen=True)
class Snap:
    """The offset to add to the moving card, and the guides to draw for each axis."""

    dx: float = 0.0
    dy: float = 0.0
    x_guides: tuple = ()
    y_guides: tuple = ()

    @property
    def guides(self):
        return self.x_guides + self.y_guides


@dataclass(frozen=True)
class _Span:
    """A footprint on one axis (lo, hi) and across it (cross_lo, cross_hi)."""

    lo: float
    hi: float
    cross_lo: float
    cross_hi: float

    @property
    def mid(self):
        return (self.lo + self.hi) / 2.0

    @property
    def cross_mid(self):
        return (self.cross_lo + self.cross_hi) / 2.0

    def shifted(self, delta):
        return _Span(self.lo + delta, self.hi + delta, self.cross_lo, self.cross_hi)

    def overlaps_across(self, other):
        return self.cross_lo < other.cross_hi and other.cross_lo < self.cross_hi


def _x_span(rect):
    return _Span(rect.left(), rect.right(), rect.top(), rect.bottom())


def _y_span(rect):
    return _Span(rect.top(), rect.bottom(), rect.left(), rect.right())


def _line_at(value, spans):
    """A guide along the snapped coordinate, across every footprint involved."""
    return (
        Guide(
            value,
            min(span.cross_lo for span in spans),
            value,
            max(span.cross_hi for span in spans),
        ),
    )


def _between(a, b):
    """Where across the axis a gap between a and b is drawn: the middle they share."""
    lo = max(a.cross_lo, b.cross_lo)
    hi = min(a.cross_hi, b.cross_hi)
    if lo <= hi:
        return (lo + hi) / 2.0
    return (a.cross_mid + b.cross_mid) / 2.0


def _gap(start, end, cross):
    return Guide(start, cross, end, cross, ticks=True)


def _candidates(moving, others):
    """Every target on this axis as (priority, delta, guides for the moved span)."""
    for other in others:
        delta = other.mid - moving.mid
        yield CENTRE, delta, lambda m, o=other: _line_at(o.mid, (m, o))

    row = sorted((other for other in others if other.overlaps_across(moving)), key=lambda s: s.lo)
    pairs = [(a, b) for a, b in pairwise(row) if b.lo - a.hi > 0]
    for a, b in pairs:
        gap = b.lo - a.hi
        for neighbour in row:

            def after(m, a=a, b=b, n=neighbour):
                return (_gap(a.hi, b.lo, _between(a, b)), _gap(n.hi, m.lo, _between(n, m)))

            def before(m, a=a, b=b, n=neighbour):
                return (_gap(a.hi, b.lo, _between(a, b)), _gap(m.hi, n.lo, _between(m, n)))

            yield EQUAL_GAP, neighbour.hi + gap - moving.lo, after
            yield EQUAL_GAP, neighbour.lo - gap - moving.hi, before

    for other in others:
        for mine in ("lo", "hi"):
            for theirs in ("lo", "hi"):
                target = getattr(other, theirs)
                delta = target - getattr(moving, mine)
                yield EDGE, delta, lambda m, o=other, t=target: _line_at(t, (m, o))

    for a, b in combinations(others, 2):
        middle = (a.mid + b.mid) / 2.0
        yield MIDPOINT, middle - moving.mid, lambda m, a=a, b=b, v=middle: _line_at(v, (m, a, b))


def _snap_axis(moving, others, radius):
    """The best target on one axis: (delta, guide builder), or (0, None) for none."""
    best = None
    for priority, delta, build in _candidates(moving, others):
        if abs(delta) > radius:
            continue
        key = (priority, abs(delta))
        if best is None or key < best[0]:
            best = (key, delta, build)
    if best is None:
        return 0.0, None
    return best[1], best[2]


def snap(moving, others, radius):
    """Where the footprint moving snaps among the footprints others"""
    others = list(others)
    if not others:
        return Snap()

    x_moving = _x_span(moving)
    y_moving = _y_span(moving)
    dx, x_build = _snap_axis(x_moving, [_x_span(rect) for rect in others], radius)
    dy, y_build = _snap_axis(y_moving, [_y_span(rect) for rect in others], radius)

    # Each axis's guides are drawn against the footprint after both snaps
    moved = moving.translated(dx, dy)
    x_guides = x_build(_x_span(moved)) if x_build else ()
    y_guides = tuple(guide.swapped() for guide in y_build(_y_span(moved))) if y_build else ()
    return Snap(dx, dy, x_guides, y_guides)


class GuideItem(QGraphicsItem):
    """The lines a dragged card has snapped to, drawn over every card while the snap holds."""

    def __init__(self):
        super().__init__()
        self._guides = ()
        self._rect = QRectF()
        self._tone = QColor(GILT_ON_DARK)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setZValue(GUIDE_Z)

    def guides(self):
        return self._guides

    def tone(self):
        return QColor(self._tone)

    def set_tone(self, color):
        """The core's color (gilt)"""
        self._tone = QColor(color)
        self.update()

    def set_guides(self, guides, view_scale=1.0):
        guides = tuple(guides)
        if guides == self._guides:
            return
        self.prepareGeometryChange()
        self._guides = guides
        rect = QRectF()
        for guide in guides:
            rect = rect.united(
                QRectF(guide.x1, guide.y1, guide.x2 - guide.x1, guide.y2 - guide.y1).normalized()
            )
        pad = (GUIDE_TICK_PX + GUIDE_HALO_PX) / max(view_scale, 1e-6)
        self._rect = rect.adjusted(-pad, -pad, pad, pad) if guides else QRectF()
        self.update()

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        if not self._guides:
            return
        world = painter.worldTransform()
        tick = GUIDE_TICK_PX / max(math.hypot(world.m11(), world.m12()), 1e-6)
        # Every halo first, so no halo darkens a core where two guides cross
        for colour, width in ((halo_for(self._tone), GUIDE_HALO_PX), (self._tone, GUIDE_CORE_PX)):
            for guide in self._guides:
                painter.setPen(guide_pen(colour, width, dashed=not guide.ticks))
                line = QLineF(guide.x1, guide.y1, guide.x2, guide.y2)
                painter.drawLine(line)
                if guide.ticks and line.length() > 0:
                    normal = line.normalVector().unitVector()
                    across = normal.p2() - normal.p1()
                    for end in (line.p1(), line.p2()):
                        painter.drawLine(end - across * tick, end + across * tick)


def halo_for(core):
    """Black under a light core, white under a dark one, translucent either way."""
    light = ground_luminance(core) > LIGHT_GROUND_LUMINANCE
    halo = QColor(Qt.GlobalColor.black if light else Qt.GlobalColor.white)
    halo.setAlphaF(GUIDE_HALO_ALPHA)
    return halo


def guide_pen(colour, width, dashed):
    """dashes are in screen pixels"""
    pen = QPen(colour)
    pen.setCosmetic(True)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    if dashed:
        pen.setDashPattern([GUIDE_DASH_PX / width, GUIDE_SPACE_PX / width])
    return pen
