import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap

from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.motion import (
    HOVER_TILT_DEG,
    LIFT_HOVER,
    LIFT_PLACED,
    LIFT_PRESSED,
    LIFT_REST,
    MOTION_EPSILON_PX,
    max_corner_delta,
)

CARD_W, CARD_H = 120, 200
FRAME = 1.0 / 60.0


class StubTab:
    """Stand in for a CanvasTab ."""

    def __init__(self, reactive=True):
        self.reactive = reactive

    def reactive_is_allowed(self):
        return self.reactive


@pytest.fixture
def card(qapp):
    def build(reactive=True, with_tab=True):
        pixmap = QPixmap(CARD_W, CARD_H)
        pixmap.fill()
        return DraggableCardItem(
            pixmap, {"id": "major_arcana/hermit"}, StubTab(reactive) if with_tab else None
        )

    return build


def run(item, frames, ambient_gain=0.0):
    for frame in range(frames):
        item.advance_motion(frame * FRAME, FRAME, ambient_gain)


def test_a_card_with_no_tab_is_inert(card):
    item = card(with_tab=False)

    item.set_orient(90)
    item.place_and_settle()

    assert item.motion.orient_lag == 0.0
    assert item.motion.lift == LIFT_REST


def test_off_teleports_the_card_through_a_rotation(card):
    item = card(reactive=False)

    item.set_orient(90)

    assert item.orient == 90
    assert item.motion.orient_lag == 0.0


def test_a_flip_takes_the_short_way_round(card):
    """359 -> 0 should be one degree."""
    item = card()
    item.set_orient(359)
    run(item, 120)

    item.set_orient(0)

    assert abs(item.motion.orient_lag) == pytest.approx(1.0)


def test_hover_lifts_the_card_and_turns_its_face_toward_the_cursor(card):
    item = card()

    item.begin_hover(QPointF(CARD_W * 0.9, CARD_H / 2))
    run(item, 60)

    assert item.motion.lift == pytest.approx(LIFT_HOVER, abs=1e-3)
    assert item.motion.face_y < 0
    assert abs(item.motion.face_y) <= HOVER_TILT_DEG + 1e-9


def test_hover_quietens_this_card_alone_rather_than_the_whole_canvas(card):
    hovered = card()
    ignored = card()
    hovered.begin_hover(QPointF(CARD_W / 2, CARD_H / 2))

    run(hovered, 60, ambient_gain=1.0)
    run(ignored, 60, ambient_gain=1.0)

    assert abs(hovered.motion.drift_x) < abs(ignored.motion.drift_x)


def test_leaving_returns_the_face_to_flat(card):
    item = card()
    item.begin_hover(QPointF(0.0, 0.0))
    run(item, 60)

    item.end_hover()
    run(item, 120)

    assert item.motion.face_x == 0.0
    assert item.motion.face_y == 0.0
    assert item.motion.lift == LIFT_REST


def test_press_settles_the_card_back_toward_the_felt(card):
    item = card()
    item.begin_hover(QPointF(CARD_W / 2, CARD_H / 2))
    run(item, 60)
    assert item.motion.lift == pytest.approx(LIFT_HOVER, abs=1e-3)

    item._pressed = True
    run(item, 60)

    assert item.motion.lift == pytest.approx(LIFT_PRESSED, abs=1e-3)
    assert LIFT_PRESSED < LIFT_HOVER


def drag(item, dx, dy, frames=30):
    item._dragging = True
    for frame in range(frames):
        item.setPos(QPointF(frame * dx, frame * dy))
        item.advance_motion(frame * FRAME, FRAME, 0.0)
    return item.motion


def test_a_drag_ploughs(card):
    "'This card fucks!'"
    channels = drag(card(), 10.0, 0.0)

    assert channels.face_y < 0  # leading (right) edge digs in
    assert channels.face_x == pytest.approx(0.0, abs=0.5)


@pytest.mark.parametrize(
    ("dx", "dy", "axis", "reason"),
    [
        (10.0, 0.0, "face_y", "dragging right digs in the right edge"),
        (-10.0, 0.0, "face_y", "dragging left digs in the left edge"),
        (0.0, 10.0, "face_x", "dragging down digs in the bottom edge"),
        (0.0, -10.0, "face_x", "dragging up digs in the top edge"),
    ],
)
def test_every_drag_direction_agrees_on_which_edge_goes_down(card, dx, dy, axis, reason):
    channels = drag(card(), dx, dy)
    tilt = getattr(channels, axis)
    displacement = dx if axis == "face_y" else dy

    assert tilt != 0.0
    assert (tilt < 0) == (displacement > 0), reason


@pytest.mark.parametrize(
    ("point", "axis", "sign"),
    [
        ((CARD_W * 0.9, CARD_H / 2), "face_y", -1),
        ((CARD_W * 0.1, CARD_H / 2), "face_y", +1),
        ((CARD_W / 2, CARD_H * 0.9), "face_x", -1),
        ((CARD_W / 2, CARD_H * 0.1), "face_x", +1),
    ],
)
def test_hover_dips_the_side_under_the_cursor_from_every_direction(card, point, axis, sign):
    item = card()
    item.begin_hover(QPointF(*point))
    run(item, 60)

    assert getattr(item.motion, axis) * sign > 0


def test_the_lean_stops_when_the_card_does(card):
    item = card()
    item._dragging = True
    drag(item, 10.0, 0.0)

    run(item, 120)  # still dragging, but no longer moving

    assert item.motion.face_y == 0.0


def test_a_dealt_card_arrives_large_and_settles_past_its_target(card):
    item = card()

    item.place_and_settle()
    assert item.motion.lift == LIFT_PLACED

    trace = []
    for frame in range(240):
        item.advance_motion(frame * FRAME, FRAME, 0.0)
        trace.append(item.motion.lift)

    assert min(trace) < LIFT_REST  # the overshoot that reads as weight
    assert trace[-1] == LIFT_REST


def test_the_shadow_follows_its_card_into_and_out_of_a_scene(qapp, card):
    from PyQt6.QtWidgets import QGraphicsScene

    item = card()
    scene = QGraphicsScene()

    scene.addItem(item)
    assert item.shadow.scene() is scene

    scene.removeItem(item)
    assert item.shadow.scene() is None


def test_a_shadow_sits_directly_beneath_its_own_card(qapp, card):
    from PyQt6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    cards = [card() for _ in range(3)]
    for depth, item in enumerate(cards, start=1):
        scene.addItem(item)
        item.setZValue(float(depth))

    painted = sorted(scene.items(), key=lambda item: item.zValue())

    assert painted == [
        cards[0].shadow,
        cards[0],
        cards[1].shadow,
        cards[1],
        cards[2].shadow,
        cards[2],
    ]


def test_the_shadow_keeps_its_place_when_the_card_is_restacked(qapp, card):
    from PyQt6.QtWidgets import QGraphicsScene

    from tarot_canvas.ui.canvas.motion import SHADOW_Z_OFFSET

    item = card()
    scene = QGraphicsScene()  # bound: a temporary scene takes the item down with it
    scene.addItem(item)

    item.setZValue(42.0)

    assert item.shadow.zValue() == 42.0 + SHADOW_Z_OFFSET


def test_the_shadow_tracks_the_card_even_with_the_clock_stopped(qapp, card):
    from PyQt6.QtWidgets import QGraphicsScene

    item = card(reactive=False)
    scene = QGraphicsScene()
    scene.addItem(item)
    before = item.shadow.pos()

    item.setPos(QPointF(400.0, 250.0))

    moved = item.shadow.pos() - before
    assert math.isclose(moved.x(), 400.0)
    assert math.isclose(moved.y(), 250.0)


# The repaint dead-band, as the card applies it


def test_ambient_drift_is_applied_in_visible_steps_rather_than_every_frame(card):
    item = card()
    applied = sum(item.advance_motion(f * FRAME, FRAME, 1.0, 1.0) for f in range(600))
    assert 0 < applied < 600 * 0.4


def test_skipped_frames_accumulate_so_drift_never_falls_behind(card):
    item = card()
    corners = item.motion.corners(CARD_W, CARD_H)
    worst = 0.0
    for frame in range(60 * 60):
        item.advance_motion(frame * FRAME, FRAME, 1.0, 1.0)
        ideal = item.motion.compose(CARD_W, CARD_H)
        shown = item.transform()
        worst = max(
            worst,
            max_corner_delta(
                [ideal.map(point) for point in corners],
                [shown.map(point) for point in corners],
            ),
        )
    assert worst < 2 * MOTION_EPSILON_PX


def test_the_dead_band_is_specified_in_device_pixels_so_it_shrinks_as_you_zoom_in(card):
    near, far = card(), card()
    at_1x = sum(near.advance_motion(f * FRAME, FRAME, 1.0, 1.0) for f in range(600))
    at_4x = sum(far.advance_motion(f * FRAME, FRAME, 1.0, 4.0) for f in range(600))
    assert at_4x > at_1x


def test_a_settling_card_lands_on_exactly_the_identity_transform(card):
    item = card()
    run(item, 60, ambient_gain=1.0)
    assert not item.transform().isIdentity()

    for frame in range(600):
        item.advance_motion(frame * FRAME, FRAME, 0.0, 1.0)
    assert item.transform().isIdentity()


def test_a_hover_is_never_deferred(card):
    item = card()
    run(item, 30, ambient_gain=0.0)
    before = item.transform()
    item.begin_hover(QPointF(CARD_W - 1, 1))
    assert item.advance_motion(1.0, FRAME, 0.0, 1.0)
    assert item.transform() != before


def test_the_shadow_keeps_its_scale_while_no_gesture_is_in_flight(card):
    item = card()
    run(item, 120, ambient_gain=1.0)
    scale, opacity = item.shadow.scale(), item.shadow.opacity()
    run(item, 120, ambient_gain=1.0)
    assert item.shadow.scale() == scale
    assert item.shadow.opacity() == opacity


def test_a_lifted_card_still_moves_its_shadow(card):
    item = card()
    resting = (item.shadow.scale(), item.shadow.opacity(), item.shadow.pos().y())
    item.begin_hover(QPointF(CARD_W / 2, CARD_H / 2))
    run(item, 60)
    assert item.motion.lift == pytest.approx(LIFT_HOVER, abs=1e-3)
    assert (item.shadow.scale(), item.shadow.opacity(), item.shadow.pos().y()) != resting


def test_the_shadow_turns_with_a_quarter_turned_card(card):
    item = card(reactive=False)

    item.set_orient(90)

    assert item.shadow.rotation() == 90
    footprint = item.shadow.sceneBoundingRect()
    assert footprint.width() > footprint.height()


def test_the_shadow_follows_the_turn_and_lands_square(card):
    item = card()
    run(item, 120)

    item.set_orient(90)
    run(item, 3)
    assert 0.0 < item.shadow.rotation() < 90.0

    run(item, 240)
    assert item.motion.orient_lag == 0.0
    assert item.shadow.rotation() == 90


def test_the_shadow_takes_no_perspective_tilt(card):
    item = card()
    item.begin_hover(QPointF(CARD_W * 0.9, CARD_H * 0.1))
    run(item, 60, ambient_gain=1.0)

    assert item.motion.face_x or item.motion.face_y
    assert item.shadow.transform().isAffine()
