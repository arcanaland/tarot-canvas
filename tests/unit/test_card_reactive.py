"""The reactive tier as seen from the card: what a hover, a press and a drag actually set.

Nothing here drives the GUI. Input handlers write *targets*; the clock chases them. That
split is what makes the tier testable at all, and these tests exercise the two halves
separately — the handler that sets the target, and the frames that converge on it.
"""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap

from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.motion import (
    HOVER_TILT_DEG,
    LEAN_MAX_DEG,
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
    """Stands in for the CanvasTab a card asks about the motion level."""

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
    """Every unit test that does not supply a tab gets the old teleporting behaviour.

    This is also the `Off` path: no per-card flag has to be kept in step with the
    preferences dialog, because the card asks the tab every time.
    """
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


def test_a_turn_is_a_lag_that_decays_rather_than_a_jump(card):
    """`orient` lands immediately so `on_flip_card` still branches on an exact value."""
    item = card()

    item.set_orient(90)
    assert item.orient == 90  # logical: immediate
    assert item.motion.orient_lag == pytest.approx(-90.0)  # visual: still where it was

    run(item, 120)
    assert item.motion.orient_lag == 0.0  # exactly, via the rest floor


def test_a_flip_takes_the_short_way_round(card):
    """359 -> 0 is one degree of travel, not 359. The modulo is the trap here."""
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
    # Cursor to the right: the right edge dips away, which this compose() spells as a
    # negative tilt_y. See test_the_tilt_signs_the_reactive_targets_are_written_against.
    assert item.motion.face_y < 0
    assert abs(item.motion.face_y) <= HOVER_TILT_DEG + 1e-9


def test_hover_quietens_this_card_alone_rather_than_the_whole_canvas(card):
    """Ambient yields to intent, per card, so the rest of the spread keeps breathing."""
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
    """Press sits *below* hover: the card is being pushed down, not picked up."""
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


def test_a_drag_ploughs_rather_than_banking(card):
    """The lean is one subtraction: the lag between visual and logical *is* the angle.

    The card ploughs — the leading edge digs in, the trailing edge lifts. `tilt_y > 0`
    recedes the *left* edge and `tilt_x > 0` recedes the *top*, so a drag whose leading
    edge goes down is negative on both axes.
    """
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
    """The regression this exists for: four signs derived independently, three of them
    disagreeing. Dragging rightward raised the leading edge while dragging downward dropped
    it, so the card inverted itself depending on which way you happened to move — which is
    unplaceable as a bug and reads only as "something feels backwards".

    One rule now covers both axes and both gestures: the tilt is the negative of the
    displacement. Pinned as a table so a future sign change has to break all four at once.
    """
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
    """The same rule, on the same channel, for the other gesture that writes it.

    Hover and drag disagreeing would be worse than either being wrong on its own: pressing
    and dragging would flip the card over as the gesture changed hands.
    """
    item = card()
    item.begin_hover(QPointF(*point))
    run(item, 60)

    assert getattr(item.motion, axis) * sign > 0


def test_a_flick_clamps_rather_than_spinning_the_card(card):
    item = card()
    item._dragging = True

    drag(item, 200.0, 200.0)  # 12000 px/s, far past anything the lean is tuned for

    assert abs(item.motion.face_x) <= LEAN_MAX_DEG + 1e-9
    assert abs(item.motion.face_y) <= LEAN_MAX_DEG + 1e-9


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


# The repaint dead-band, as the card applies it


def test_ambient_drift_is_applied_in_visible_steps_rather_than_every_frame(card):
    """The fix for the canvas pinning a core: sub-pixel changes do not re-rasterise.

    Ambient motion moves a corner by well under a tenth of a pixel per frame, and every
    one of those used to cost a full transformed-pixmap repaint.
    """
    item = card()
    applied = sum(item.advance_motion(f * FRAME, FRAME, 1.0, 1.0) for f in range(600))
    assert 0 < applied < 600 * 0.4


def test_skipped_frames_accumulate_so_drift_never_falls_behind(card):
    """The dead-band defers the repaint; it must not drop the motion.

    Every comparison is against the last transform *applied*, so the gap between what the
    channels say and what the card shows stays bounded by roughly one threshold. Comparing
    against the previous frame instead would let the error integrate without limit.
    """
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
    """A threshold in item coordinates would become visible at 4x. This one does not."""
    near, far = card(), card()
    at_1x = sum(near.advance_motion(f * FRAME, FRAME, 1.0, 1.0) for f in range(600))
    at_4x = sum(far.advance_motion(f * FRAME, FRAME, 1.0, 4.0) for f in range(600))
    assert at_4x > at_1x


def test_a_settling_card_lands_on_exactly_the_identity_transform(card):
    """The one state the dead-band must never swallow.

    The final step onto zero is by construction the smallest one, so a naive threshold
    would leave a faded-out card holding a permanent sliver of tilt — and repainting for
    it, which is the defect AMBIENT_GAIN_FLOOR exists to prevent.
    """
    item = card()
    run(item, 60, ambient_gain=1.0)
    assert not item.transform().isIdentity()

    for frame in range(600):
        item.advance_motion(frame * FRAME, FRAME, 0.0, 1.0)
    assert item.transform().isIdentity()


def test_a_hover_is_never_deferred(card):
    """Reactive deltas are an order of magnitude above the band, so intent is immediate."""
    item = card()
    run(item, 30, ambient_gain=0.0)
    before = item.transform()
    item.begin_hover(QPointF(CARD_W - 1, 1))
    assert item.advance_motion(1.0, FRAME, 0.0, 1.0)
    assert item.transform() != before
