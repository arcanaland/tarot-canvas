"""Arrangement must measure the logical position, not the drifting visual one.

Cards carry a live ambient transform once RFC-024 phase 3 lands. If align and distribute
read `sceneBoundingRect()` they read a value that changes every frame, so the same command
gives a different answer each time it runs — and running it twice moves the cards twice.
"""

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsRectItem

from tarot_canvas.ui.canvas.alignment import (
    align_items_horizontally,
    align_items_vertically,
    distribute_items_horizontally,
    distribute_items_vertically,
)
from tarot_canvas.ui.canvas.motion import MotionChannels

ARRANGEMENTS = [
    (align_items_horizontally, "left"),
    (align_items_horizontally, "center"),
    (align_items_horizontally, "right"),
    (align_items_vertically, "top"),
    (align_items_vertically, "center"),
    (align_items_vertically, "bottom"),
    (distribute_items_horizontally, None),
    (distribute_items_vertically, None),
]

# Mid-breath: a tilt and an offset well inside what the ambient tier actually produces.
DRIFTING = MotionChannels(tilt_x=2.4, tilt_y=-1.7, drift_x=1.3, drift_y=-0.9)


def make_items(count, drifting):
    items = []
    for i in range(count):
        item = QGraphicsRectItem(QRectF(0, 0, 300, 450))
        item.setPos((i * 137) % 1000, (i * 241) % 1000)
        if drifting:
            item.setTransform(DRIFTING.compose(300, 450))
        items.append(item)
    return items


def run(arrangement, argument, items):
    if argument is None:
        arrangement(items)
    else:
        arrangement(items, argument)


@pytest.mark.parametrize("arrangement,argument", ARRANGEMENTS)
def test_arrangement_ignores_a_live_ambient_transform(qapp, arrangement, argument):
    still = make_items(5, drifting=False)
    drifting = make_items(5, drifting=True)

    run(arrangement, argument, still)
    run(arrangement, argument, drifting)

    for a, b in zip(still, drifting, strict=True):
        assert a.pos().x() == pytest.approx(b.pos().x(), abs=1e-9)
        assert a.pos().y() == pytest.approx(b.pos().y(), abs=1e-9)


@pytest.mark.parametrize("arrangement,argument", ARRANGEMENTS)
def test_arrangement_is_idempotent_while_drifting(qapp, arrangement, argument):
    """Running the same align twice must not move anything the second time."""
    items = make_items(5, drifting=True)

    run(arrangement, argument, items)
    once = [(i.pos().x(), i.pos().y()) for i in items]
    run(arrangement, argument, items)

    for (x, y), item in zip(once, items, strict=True):
        assert item.pos().x() == pytest.approx(x, abs=1e-9)
        assert item.pos().y() == pytest.approx(y, abs=1e-9)
