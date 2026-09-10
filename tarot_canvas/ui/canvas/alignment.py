import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

DEFAULT_CIRCLE_GAP_RATIO = 0.15


def logical_rect(item):
    rect = item.boundingRect()
    quarter_turns = round(item.rotation() / 90) % 4
    if quarter_turns:
        origin = item.transformOriginPoint()
        turn = QTransform().translate(origin.x(), origin.y())
        turn.rotate(quarter_turns * 90)
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


def solve_circle_radius(width, height, count, gap=None):
    """Smallest radius at which `count` upright width x height cards do not overlap."""
    if count < 2:
        return 0.0

    if gap is None:
        gap = DEFAULT_CIRCLE_GAP_RATIO * min(width, height)

    need_x = width + gap
    need_y = height + gap
    step = 2 * math.pi / count
    half_chord = math.sin(step / 2)

    radius = 0.0
    for i in range(count):
        phi = i * step + step / 2  # bisector of the pair (i, i + 1)
        reach = max(abs(math.sin(phi)) / need_x, abs(math.cos(phi)) / need_y)
        radius = max(radius, 1.0 / (2 * half_chord * reach))
    return radius


def arrange_items_in_circle(items, gap=None):
    """Arrange items in a circle while preserving their upright/reversed orientation"""
    if not items:
        return

    card_width = max(item.boundingRect().width() for item in items)
    card_height = max(item.boundingRect().height() for item in items)

    centers = [item.pos() + item.boundingRect().center() for item in items]
    center = QPointF(
        sum(p.x() for p in centers) / len(centers),
        sum(p.y() for p in centers) / len(centers),
    )

    radius = solve_circle_radius(card_width, card_height, len(items), gap)

    for i, item in enumerate(items):
        angle = (i / len(items)) * 2 * math.pi
        target = QPointF(
            center.x() + radius * math.cos(angle),
            center.y() + radius * math.sin(angle),
        )
        item.setPos(target - item.boundingRect().center())
