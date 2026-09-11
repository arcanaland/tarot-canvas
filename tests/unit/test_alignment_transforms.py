import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsRectItem

from tarot_canvas.ui.canvas.alignment import (
    align_items_horizontally,
    align_items_vertically,
    distribute_items_horizontally,
    distribute_items_vertically,
)
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
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


@pytest.mark.parametrize("rotation", [90, 270])
@pytest.mark.parametrize(
    "arrangement,argument,edge",
    [
        (align_items_horizontally, "left", QRectF.left),
        (align_items_horizontally, "right", QRectF.right),
        (align_items_vertically, "top", QRectF.top),
        (align_items_vertically, "bottom", QRectF.bottom),
    ],
)
def test_edge_alignment_sees_a_card_turned_sideways(qapp, arrangement, argument, edge, rotation):
    """A rotate-90 card is measured by its turned footprint"""
    upright = QGraphicsRectItem(QRectF(0, 0, 300, 450))
    upright.setPos(0, 0)
    sideways = QGraphicsRectItem(QRectF(0, 0, 300, 450))
    sideways.setPos(40, 600)
    sideways.setTransformOriginPoint(150, 225)
    sideways.setRotation(rotation)

    arrangement([upright, sideways], argument)

    assert edge(sideways.sceneBoundingRect()) == pytest.approx(
        edge(upright.sceneBoundingRect()), abs=1e-9
    )


@pytest.mark.parametrize("orient", [90, 270])
@pytest.mark.parametrize(
    "arrangement,argument,edge",
    [
        (align_items_horizontally, "left", QRectF.left),
        (align_items_horizontally, "right", QRectF.right),
        (align_items_vertically, "top", QRectF.top),
        (align_items_vertically, "bottom", QRectF.bottom),
    ],
)
def test_edge_alignment_sees_a_card_oriented_sideways(qapp, arrangement, argument, edge, orient):
    """A card's orientation lives in its motion transform, not in item.rotation()"""
    pixmap = QPixmap(300, 450)
    pixmap.fill()
    upright = DraggableCardItem(pixmap, {"id": "upright"})
    sideways = DraggableCardItem(pixmap, {"id": "sideways"})
    sideways.setPos(40, 600)
    sideways.set_orient(orient)

    arrangement([upright, sideways], argument)

    assert edge(sideways.sceneBoundingRect()) == pytest.approx(
        edge(upright.sceneBoundingRect()), abs=1e-6
    )
