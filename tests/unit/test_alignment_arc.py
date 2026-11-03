import math
from itertools import pairwise

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsRectItem

from tarot_canvas.ui.canvas.alignment import (
    DEFAULT_CIRCLE_GAP_RATIO,
    arc_angles,
    arrange_items_on_arc,
    centre_of,
    fold_follow,
    measured_gap,
    solve_arc_radius,
)

# (width, height): a 300x450 default card, h32, a landscape card and a square
CARD_SIZES = [(300, 450), (20, 32), (450, 300), (300, 300)]
COUNTS = [1, 2, 3, 4, 5, 6, 7, 10, 13, 22, 36, 78]


def make_items(count, width, height, spread=1000):
    """`count` items scattered deterministically, so the arrangement has work to do."""
    items = []
    for i in range(count):
        item = QGraphicsRectItem(QRectF(0, 0, width, height))
        item.setPen(QPen(Qt.PenStyle.NoPen))  # so the bounding rect is the card
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


def footprint(item):
    """The item's outline in the scene, turned by its rotation"""
    return item.mapToScene(item.boundingRect())


def centre(item):
    return item.pos() + item.boundingRect().center()


# -- never overlapping, at any bend --------------------------------------------

BENDS = [360, 180, 90, 15, 0, -90, -180, -360]


def assert_no_overlap(items):
    outlines = [footprint(item) for item in items]
    for i, a in enumerate(outlines):
        for b in outlines[i + 1 :]:
            assert not a.intersects(b)


@pytest.mark.parametrize("bend", BENDS)
@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_arrangement_never_overlaps(qapp, count, width, height, bend):
    items = make_items(count, width, height)
    arrange_items_on_arc(items, bend=bend)
    assert worst_overlap_fraction(items) == 0.0


@pytest.mark.parametrize("bend", [360, 180, 0, -180])
@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_arrangement_leaves_the_requested_gap(qapp, count, width, height, bend):
    """Upright cards clear each other by `gap` on at least one axis, not merely by touching."""
    gap = 40.0
    items = make_items(count, width, height)
    arrange_items_on_arc(items, bend=bend, gap=gap / width)

    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            dx = abs(centre(a).x() - centre(b).x())
            dy = abs(centre(a).y() - centre(b).y())
            # Allow a hair of float slack on the pair that is exactly at the bound.
            assert dx >= width + gap - 1e-6 or dy >= height + gap - 1e-6


@pytest.mark.parametrize("count", [3, 7, 22, 78])
@pytest.mark.parametrize("bend", BENDS)
def test_following_cards_never_overlap(qapp, count, bend):
    items = make_items(count, 100, 171)
    arrange_items_on_arc(items, bend=bend, follow=True)
    assert_no_overlap(items)


@pytest.mark.parametrize("turn", [0, 45, 90, -135])
@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("bend", [180, 0, -90])
def test_a_turned_arc_never_overlaps(qapp, turn, follow, bend):
    items = make_items(7, 100, 171)
    arrange_items_on_arc(items, bend=bend, turn=turn, follow=follow)
    assert_no_overlap(items)


@pytest.mark.parametrize("width,height", CARD_SIZES)
@pytest.mark.parametrize("count", COUNTS)
def test_on_a_ring_adjacent_pairs_are_the_binding_constraint(count, width, height):
    """At 360 no pair of cards needs more room than some pair of neighbours."""
    if count < 2:
        pytest.skip("no pairs")
    gap = 0.15 * min(width, height)
    angles = [math.radians(a) for a in arc_angles(count, 360)]
    all_pairs = max(
        1.0
        / (
            2
            * abs(math.sin((b - a) / 2))
            * max(
                abs(math.sin((a + b) / 2)) / (width + gap),
                abs(math.cos((a + b) / 2)) / (height + gap),
            )
        )
        for i, a in enumerate(angles)
        for b in angles[i + 1 :]
    )
    assert solve_arc_radius(width, height, arc_angles(count, 360), gap) == pytest.approx(
        all_pairs, rel=1e-12
    )


def test_radius_scales_with_card_size():
    angles = arc_angles(10, 360)
    big = solve_arc_radius(300, 450, angles, 0.15 * 300)
    small = solve_arc_radius(20, 32, angles, 0.15 * 20)
    assert small < 100
    assert big / small == pytest.approx(300 / 20, rel=0.15)


def test_single_item_is_left_at_the_center(qapp):
    items = make_items(1, 300, 450)
    before = items[0].pos()
    arrange_items_on_arc(items)
    assert items[0].pos() == before


def test_empty_selection_is_a_noop(qapp):
    arrange_items_on_arc([])


def test_measurement_ignores_item_transforms(qapp):
    """Arrangement measures pos(), so a card's own rotation/scale must not move it."""
    plain = make_items(5, 300, 450)
    arrange_items_on_arc(plain)
    plain_positions = [(i.pos().x(), i.pos().y()) for i in plain]

    transformed = make_items(5, 300, 450)
    for item in transformed:
        item.setTransformOriginPoint(150, 225)
        item.setRotation(0.8)
        item.setScale(1.02)
    arrange_items_on_arc(transformed)

    for (px, py), item in zip(plain_positions, transformed, strict=True):
        assert item.pos().x() == pytest.approx(px)
        assert item.pos().y() == pytest.approx(py)


# -- the shape the bend gives ---------------------------------------------------


def test_each_card_takes_an_equal_share_of_the_bend():
    assert arc_angles(4, 360) == [-225, -135, -45, 45]
    assert arc_angles(5, 180) == [-162, -126, -90, -54, -18]


def test_a_bend_down_puts_the_middle_at_the_bottom():
    assert arc_angles(3, -180) == [150, 90, 30]


def test_the_other_direction_numbers_the_other_way():
    assert arc_angles(3, 180, clockwise=False) == [-30, -90, -150]


def test_turn_rotates_the_whole_arc():
    assert arc_angles(3, 180, turn=90) == [-60, 0, 60]


def test_the_bend_changes_smoothly_down_to_a_ring():
    """No step in the angles as the bend nears 360: 345 is nearly the ring"""
    ring = arc_angles(6, 360)
    nearly = arc_angles(6, 345)
    assert max(abs(a - b) for a, b in zip(ring, nearly, strict=True)) < 10


def test_the_radius_changes_smoothly_down_to_a_ring():
    width, height, gap = 100, 171, 15
    ring = solve_arc_radius(width, height, arc_angles(6, 360), gap, follow=True)
    nearly = solve_arc_radius(width, height, arc_angles(6, 345), gap, follow=True)
    assert nearly == pytest.approx(ring, rel=0.1)


def centres(items):
    return [centre(item) for item in items]


@pytest.mark.parametrize("bend", [180, 90, 15, 0, -15, -90, -180])
def test_cards_read_left_to_right_however_it_bends(qapp, bend):
    items = make_items(5, 300, 450)
    arrange_items_on_arc(items, bend=bend)
    xs = [c.x() for c in centres(items)]
    assert xs == sorted(xs)


def test_a_bend_up_is_a_rainbow(qapp):
    items = make_items(5, 300, 450)
    arrange_items_on_arc(items, bend=180)
    ys = [c.y() for c in centres(items)]
    assert min(range(5), key=lambda i: ys[i]) == 2, "the middle card is highest"


def test_a_bend_down_is_a_bowl(qapp):
    items = make_items(5, 300, 450)
    arrange_items_on_arc(items, bend=-180)
    ys = [c.y() for c in centres(items)]
    assert max(range(5), key=lambda i: ys[i]) == 2, "the middle card is lowest"


@pytest.mark.parametrize("follow", [False, True])
def test_no_bend_is_a_straight_row_a_width_and_gap_apart(qapp, follow):
    items = make_items(4, 100, 171)
    arrange_items_on_arc(items, bend=0, follow=follow, gap=0.25)
    points = centres(items)
    assert len({round(p.y(), 9) for p in points}) == 1
    steps = [b.x() - a.x() for a, b in pairwise(points)]
    assert steps == pytest.approx([125, 125, 125])
    assert [item.rotation() for item in items] == [0, 0, 0, 0]


def test_a_turned_straight_row_runs_along_the_turn(qapp):
    items = make_items(3, 100, 171)
    arrange_items_on_arc(items, bend=0, turn=90, follow=True)
    points = centres(items)
    assert len({round(p.x(), 9) for p in points}) == 1
    assert points[0].y() < points[1].y() < points[2].y(), "down the screen"
    assert [item.rotation() % 360 for item in items] == [90, 90, 90]


def test_a_slight_bend_is_nearly_the_straight_row(qapp):
    straight = make_items(5, 100, 171)
    arrange_items_on_arc(straight, bend=0)
    slight = make_items(5, 100, 171)
    arrange_items_on_arc(slight, bend=15)
    for a, b in zip(centres(straight), centres(slight), strict=True):
        assert (a - b).manhattanLength() < 0.2 * 100


@pytest.mark.parametrize(
    "degrees,folded",
    [(0, 0), (45, 45), (90, 90), (135, -45), (180, 0), (225, 45), (270, 90), (-90, 90), (-45, -45)],
)
def test_fold_follow_keeps_a_card_off_its_head(degrees, folded):
    assert fold_follow(degrees) == pytest.approx(folded)


def test_following_cards_turn_their_tops_outward(qapp):
    items = make_items(4, 100, 171)
    arrange_items_on_arc(items, bend=360, follow=True, turn=45)
    # 9, 12, 3 and 6 o'clock
    assert [item.rotation() % 360 for item in items] == pytest.approx([90, 0, 90, 0])


def test_upright_turns_a_card_back(qapp):
    items = make_items(3, 100, 171)
    for item in items:
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(90)
    arrange_items_on_arc(items)
    assert [item.rotation() for item in items] == [0, 0, 0]


def test_a_following_ring_of_the_whole_deck_is_far_smaller():
    width, height = 100, 171
    angles = arc_angles(78, 360)
    gap = DEFAULT_CIRCLE_GAP_RATIO * width
    upright = solve_arc_radius(width, height, angles, gap)
    follow = solve_arc_radius(width, height, angles, gap, follow=True)
    assert follow < 0.6 * upright
    assert follow / width == pytest.approx(15.1, abs=0.1)
    assert upright / width == pytest.approx(27, abs=1)


@pytest.mark.parametrize("bend", [360, 90, 0, -180])
@pytest.mark.parametrize("follow", [False, True])
def test_the_cards_centroid_is_the_one_given(qapp, bend, follow):
    items = make_items(6, 300, 450)
    target = QPointF(-123.5, 456.25)
    arrange_items_on_arc(items, bend=bend, follow=follow, centroid=target)
    after = centre_of(items)
    assert after.x() == pytest.approx(target.x(), abs=1e-6)
    assert after.y() == pytest.approx(target.y(), abs=1e-6)


def test_without_a_centroid_the_selection_stays_centred(qapp):
    items = make_items(6, 300, 450)
    before = centre_of(items)
    arrange_items_on_arc(items, bend=90)
    after = centre_of(items)
    assert after.x() == pytest.approx(before.x(), abs=1e-6)
    assert after.y() == pytest.approx(before.y(), abs=1e-6)


# -- the measured gap ---------------------------------------------------------


def test_the_gap_is_measured_from_the_cards(qapp):
    items = make_items(3, 100, 171)
    for i, item in enumerate(items):
        item.setPos(i * 140, 0)
    assert measured_gap(items) == pytest.approx(0.4)


def test_stacked_cards_fall_back_to_the_default_gap(qapp):
    items = make_items(3, 100, 171)
    for item in items:
        item.setPos(0, 0)
    assert measured_gap(items) == DEFAULT_CIRCLE_GAP_RATIO


def test_the_gap_is_measured_corner_to_corner(qapp):
    items = make_items(2, 100, 171)
    items[1].setPos(130, 211)
    assert measured_gap(items) == pytest.approx(0.5)
