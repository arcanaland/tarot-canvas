import math
from itertools import pairwise
from statistics import median

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

DEFAULT_CIRCLE_GAP_RATIO = 0.15


def _turn(item):
    """The item's logical rotation in degrees and the point it turns about."""
    orient = getattr(item, "orient", None)
    if orient is not None:
        rect = item.boundingRect()
        return orient, QPointF(rect.width() / 2.0, rect.height() / 2.0)
    return item.rotation(), item.transformOriginPoint()


def logical_rect(item):
    """The item's footprint in scene coordinates: the box around it turned by its true angle."""
    rect = item.boundingRect()
    degrees, origin = _turn(item)
    if degrees % 360:
        turn = QTransform().translate(origin.x(), origin.y())
        turn.rotate(degrees)
        turn.translate(-origin.x(), -origin.y())
        rect = turn.mapRect(rect)
    return rect.translated(item.pos())


def align_items_horizontally(items, alignment):
    """Align items horizontally"""
    if not items:
        return

    if alignment == "left":
        leftmost = min(logical_rect(item).left() for item in items)
        # Align all to leftmost edge
        for item in items:
            item_rect = logical_rect(item)
            offset = leftmost - item_rect.left()
            item.setPos(item.pos().x() + offset, item.pos().y())

    elif alignment == "center":
        avg_center_x = sum(logical_rect(item).center().x() for item in items) / len(items)
        # Align all to average center
        for item in items:
            item_rect = logical_rect(item)
            offset = avg_center_x - item_rect.center().x()
            item.setPos(item.pos().x() + offset, item.pos().y())

    elif alignment == "right":
        rightmost = max(logical_rect(item).right() for item in items)
        # Align all to rightmost edge
        for item in items:
            item_rect = logical_rect(item)
            offset = rightmost - item_rect.right()
            item.setPos(item.pos().x() + offset, item.pos().y())


def align_items_vertically(items, alignment):
    """Align items vertically"""
    if not items:
        return

    if alignment == "top":
        topmost = min(logical_rect(item).top() for item in items)
        # Align all to topmost edge
        for item in items:
            item_rect = logical_rect(item)
            offset = topmost - item_rect.top()
            item.setPos(item.pos().x(), item.pos().y() + offset)

    elif alignment == "center":
        avg_center_y = sum(logical_rect(item).center().y() for item in items) / len(items)
        # Align all to average center
        for item in items:
            item_rect = logical_rect(item)
            offset = avg_center_y - item_rect.center().y()
            item.setPos(item.pos().x(), item.pos().y() + offset)

    elif alignment == "bottom":
        bottommost = max(logical_rect(item).bottom() for item in items)
        # Align all to bottommost edge
        for item in items:
            item_rect = logical_rect(item)
            offset = bottommost - item_rect.bottom()
            item.setPos(item.pos().x(), item.pos().y() + offset)


def distribute_items_horizontally(items):
    """Distribute items horizontally with equal spacing"""
    if len(items) < 3:
        return  # Need at least 3 items to distribute

    # Sort items by x position
    sorted_items = sorted(items, key=lambda item: logical_rect(item).center().x())

    # Get leftmost and rightmost positions
    left_edge = logical_rect(sorted_items[0]).center().x()
    right_edge = logical_rect(sorted_items[-1]).center().x()

    # Calculate equal spacing
    total_width = right_edge - left_edge
    spacing = total_width / (len(sorted_items) - 1) if len(sorted_items) > 1 else 0

    # Reposition middle items
    for i in range(1, len(sorted_items) - 1):
        item = sorted_items[i]
        target_x = left_edge + (i * spacing)
        current_center = logical_rect(item).center()
        offset_x = target_x - current_center.x()
        item.setPos(item.pos().x() + offset_x, item.pos().y())


def distribute_items_vertically(items):
    """Distribute items vertically with equal spacing"""
    if len(items) < 3:
        return  # Need at least 3 items to distribute

    # Sort items by y position
    sorted_items = sorted(items, key=lambda item: logical_rect(item).center().y())

    # Get topmost and bottommost positions
    top_edge = logical_rect(sorted_items[0]).center().y()
    bottom_edge = logical_rect(sorted_items[-1]).center().y()

    # Calculate equal spacing
    total_height = bottom_edge - top_edge
    spacing = total_height / (len(sorted_items) - 1) if len(sorted_items) > 1 else 0

    # Reposition middle items
    for i in range(1, len(sorted_items) - 1):
        item = sorted_items[i]
        target_y = top_edge + (i * spacing)
        current_center = logical_rect(item).center()
        offset_y = target_y - current_center.y()
        item.setPos(item.pos().x(), item.pos().y() + offset_y)


def arc_angles(count, sweep=360, start=90, clockwise=True):
    """Where each of `count` cards sits, in scene degrees (from 3 o'clock, clockwise on screen).

    `start` is in degrees clockwise from 12 o'clock. A full sweep spaces the cards evenly
    round the ring; anything less puts the first and last cards at its two ends.
    """
    if count < 1:
        return []
    if count == 1:
        step = 0.0
    elif sweep >= 360:
        step = 360.0 / count
    else:
        step = sweep / (count - 1)
    if not clockwise:
        step = -step
    return [start - 90.0 + i * step for i in range(count)]


def fold_follow(degrees):
    """A turn folded into (-90, 90], so a card following the arc never stands on its head."""
    return 90.0 - (90.0 - degrees) % 180.0


def _pair_radius(width, height, a, b, gap, follow):
    """Smallest radius at which the cards at scene angles `a` and `b` (degrees) clear each other."""
    half = math.radians(b - a) / 2
    half_chord = abs(math.sin(half))
    if half_chord < 1e-12:
        return math.inf
    if follow:
        # The chord at the cards' inner edges must clear a width and the gap
        return (width + gap) / (2 * half_chord) + height / 2
    bisector = math.radians(a) + half
    reach = max(abs(math.sin(bisector)) / (width + gap), abs(math.cos(bisector)) / (height + gap))
    return 1.0 / (2 * half_chord * reach)


def solve_arc_radius(width, height, angles, gap, follow=False):
    """Smallest radius at which width x height cards at `angles` (degrees) do not overlap.

    Upright cards clear a neighbour by `gap` on at least one axis; following cards clear it
    along their inner edges. Adjacent cards are checked, and so are the first and last,
    which a full ring makes neighbours and a nearly full one brings close.
    """
    if len(angles) < 2:
        return 0.0
    pairs = list(pairwise(angles))
    if len(angles) > 2:
        pairs.append((angles[-1], angles[0]))
    return max(_pair_radius(width, height, a, b, gap, follow) for a, b in pairs)


def _edge_distance(a, b):
    dx = max(0.0, a.left() - b.right(), b.left() - a.right())
    dy = max(0.0, a.top() - b.bottom(), b.top() - a.bottom())
    return math.hypot(dx, dy)


def measured_gap(items):
    """The selection's own spacing, in card widths: the median distance to the nearest card."""
    if len(items) < 2:
        return DEFAULT_CIRCLE_GAP_RATIO
    width = max(item.boundingRect().width() for item in items)
    rects = [logical_rect(item) for item in items]
    typical = median(
        min(_edge_distance(rect, other) for j, other in enumerate(rects) if j != i)
        for i, rect in enumerate(rects)
    )
    if typical <= 0 or width <= 0:
        return DEFAULT_CIRCLE_GAP_RATIO
    return typical / width


def centre_of(items):
    """The mean of the items' centres in the scene"""
    centres = [item.pos() + item.boundingRect().center() for item in items]
    return QPointF(
        sum(p.x() for p in centres) / len(centres),
        sum(p.y() for p in centres) / len(centres),
    )


def set_turn(item, degrees):
    """Turn an item to `degrees`: a card through its orient, anything else about its centre"""
    if hasattr(item, "set_orient"):
        item.set_orient(degrees)
    else:
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(degrees)


def arrange_items_on_arc(
    items,
    *,
    sweep=360,
    start=90,
    clockwise=True,
    follow=False,
    gap=DEFAULT_CIRCLE_GAP_RATIO,
    centroid=None,
):
    """Put `items`, in the order given, round an arc whose cards are centred on `centroid`.

    `gap` is in card widths. Upright cards are turned to 0; following cards turn their tops
    outward. A card's reversal is left alone. With no `centroid`, the items' own is kept.
    """
    if not items:
        return
    if centroid is None:
        centroid = centre_of(items)

    width = max(item.boundingRect().width() for item in items)
    height = max(item.boundingRect().height() for item in items)
    angles = arc_angles(len(items), sweep, start, clockwise)
    radius = solve_arc_radius(width, height, angles, gap * width, follow)

    points = [
        (radius * math.cos(math.radians(a)), radius * math.sin(math.radians(a))) for a in angles
    ]
    # Offset the circle so the cards' own centroid stays where the selection's was
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    origin = QPointF(centroid.x() - mean_x, centroid.y() - mean_y)

    for item, angle, (x, y) in zip(items, angles, points, strict=True):
        item.setPos(origin + QPointF(x, y) - item.boundingRect().center())
        set_turn(item, fold_follow(angle + 90.0) if follow else 0.0)
