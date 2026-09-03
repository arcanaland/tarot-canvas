import math

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsRectItem

from tarot_canvas.ui.canvas.alignment import arrange_items_in_circle, solve_circle_radius

# (width, height): a 300x450 default card, h32, a landscape card and a square
CARD_SIZES = [(300, 450), (20, 32), (450, 300), (300, 300)]
COUNTS = [1, 2, 3, 4, 5, 6, 7, 10, 13, 22, 36, 78]


def make_items(count, width, height, spread=1000):
    """`count` items scattered deterministically, so the arrangement has work to do."""
    items = []
    for i in range(count):
        item = QGraphicsRectItem(QRectF(0, 0, width, height))
        item.setPos((i * 137) % spread, (i * 241) % spread)
        items.append(item)
    return items


def worst_overlap_fraction(items):
    """Largest pairwise intersection, as a fraction of one card's area."""
    worst = 0.0
    for i, a in enumerate(items):
        rect_a = a.boundingRect().translated(a.pos())
        for b in items[i + 1 :]:
            rect_b = b.boundingRect().translated(b.pos())
            overlap = rect_a.intersected(rect_b)
            if not overlap.isEmpty():
                worst = max(
                    worst, overlap.width() * overlap.height() / (rect_a.width() * rect_a.height())
                )
    return worst


@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_arrangement_never_overlaps(qapp, count, width, height):
    items = make_items(count, width, height)
    arrange_items_in_circle(items)
    assert worst_overlap_fraction(items) == 0.0


@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_arrangement_leaves_the_requested_gap(qapp, count, width, height):
    """Cards clear each other by `gap` on at least one axis, not merely by touching."""
    gap = 40.0
    items = make_items(count, width, height)
    arrange_items_in_circle(items, gap=gap)

    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            dx = abs((a.pos().x() + width / 2) - (b.pos().x() + width / 2))
            dy = abs((a.pos().y() + height / 2) - (b.pos().y() + height / 2))
            # Allow a hair of float slack on the pair that is exactly at the bound.
            assert dx >= width + gap - 1e-6 or dy >= height + gap - 1e-6


@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_adjacent_pairs_are_the_binding_constraint(count, width, height):
    if count < 2:
        pytest.skip("no pairs")
    gap = 0.15 * min(width, height)
    step = 2 * math.pi / count
    all_pairs = max(
        1.0
        / (
            2
            * math.sin(k * math.pi / count)
            * max(
                abs(math.sin((i + k / 2) * step)) / (width + gap),
                abs(math.cos((i + k / 2) * step)) / (height + gap),
            )
        )
        for k in range(1, count // 2 + 1)
        for i in range(count)
    )
    assert solve_circle_radius(width, height, count) == pytest.approx(all_pairs, rel=1e-12)


def test_radius_scales_with_card_size():
    big = solve_circle_radius(300, 450, 10)
    small = solve_circle_radius(20, 32, 10)
    assert small < 100
    assert big / small == pytest.approx(300 / 20, rel=0.15)


def test_single_item_is_left_at_the_center(qapp):
    items = make_items(1, 300, 450)
    before = items[0].pos()
    arrange_items_in_circle(items)
    assert items[0].pos() == before


def test_empty_selection_is_a_noop(qapp):
    arrange_items_in_circle([])


def test_arrangement_is_centered_on_the_selection(qapp):
    items = make_items(6, 300, 450)
    centers = [i.pos() + i.boundingRect().center() for i in items]
    before_x = sum(p.x() for p in centers) / len(centers)
    before_y = sum(p.y() for p in centers) / len(centers)

    arrange_items_in_circle(items)

    centers = [i.pos() + i.boundingRect().center() for i in items]
    assert sum(p.x() for p in centers) / len(centers) == pytest.approx(before_x, abs=1e-6)
    assert sum(p.y() for p in centers) / len(centers) == pytest.approx(before_y, abs=1e-6)


def test_measurement_ignores_the_wobble_transform(qapp):
    plain = make_items(5, 300, 450)
    arrange_items_in_circle(plain)
    plain_positions = [(i.pos().x(), i.pos().y()) for i in plain]

    wobbling = make_items(5, 300, 450)
    for item in wobbling:
        item.setTransformOriginPoint(150, 225)
        item.setRotation(0.8)
        item.setScale(1.02)
    arrange_items_in_circle(wobbling)

    for (px, py), item in zip(plain_positions, wobbling, strict=True):
        assert item.pos().x() == pytest.approx(px)
        assert item.pos().y() == pytest.approx(py)
