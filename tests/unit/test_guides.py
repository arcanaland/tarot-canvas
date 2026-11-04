import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

from tarot_canvas.ui.canvas.guides import Snap, snap

W, H = 100.0, 160.0


def card(x, y, w=W, h=H):
    return QRectF(x, y, w, h)


def turned(rect, degrees):
    """rect's footprint turned about its centre, as alignment.logical_rect builds it."""
    centre = rect.center()
    turn = QTransform().translate(centre.x(), centre.y())
    turn.rotate(degrees)
    turn.translate(-centre.x(), -centre.y())
    return turn.mapRect(rect)


# Centre


def test_a_card_five_units_off_a_centre_line_snaps_onto_it():
    result = snap(card(305, 400), [card(300, 0)], 8)
    assert result.dx == pytest.approx(-5)
    assert result.dy == 0
    assert len(result.x_guides) == 1
    assert result.y_guides == ()


def test_a_card_nine_units_off_does_not_snap_at_radius_eight():
    result = snap(card(309, 400), [card(300, 0)], 8)
    assert result == Snap()


def test_a_centre_line_snaps_on_the_y_axis_too():
    result = snap(card(400, 5), [card(0, 0)], 8)
    assert result.dy == pytest.approx(-5)
    assert result.dx == 0
    assert len(result.y_guides) == 1


def test_a_centre_guide_runs_along_the_snapped_line_across_both_cards():
    result = snap(card(305, 400), [card(300, 0)], 8)
    (guide,) = result.x_guides
    assert guide.x1 == guide.x2 == pytest.approx(350)
    assert guide.y1 == pytest.approx(0)
    assert guide.y2 == pytest.approx(560)


def test_centre_beats_a_nearer_edge():
    # Left edges 1 apart; the narrow card's centre 6 from the moving one's
    other = card(1, 0, w=W - 12)
    result = snap(card(0, 400), [other], 8)
    assert result.dx == pytest.approx(other.center().x() - 50)


def test_the_nearest_wins_within_one_priority():
    result = snap(card(0, 400), [card(6, 0), card(-3, 1000)], 8)
    assert result.dx == pytest.approx(-3)


# Equal gap


def three_card(third_x, third_y=0.0):
    """Adam's Three-Card: two cards a 0.4-width gap apart, the third dropped to their right."""
    gap = 0.4 * W
    first = card(0, 0)
    second = card(W + gap, 0)
    return first, second, card(third_x, third_y)


def test_the_third_card_snaps_to_the_first_pairs_gap():
    gap = 0.4 * W
    first, second, third = three_card(2 * W + 2 * gap + 3, third_y=1)
    result = snap(third, [first, second], 8)
    assert third.left() + result.dx == pytest.approx(second.right() + gap)


def test_an_equal_gap_draws_both_gaps_with_ticks():
    gap = 0.4 * W
    first, second, third = three_card(2 * W + 2 * gap + 3, third_y=1)
    result = snap(third, [first, second], 8)
    reference, mine = result.x_guides
    assert reference.ticks and mine.ticks
    assert (reference.x1, reference.x2) == (pytest.approx(W), pytest.approx(W + gap))
    assert (mine.x1, mine.x2) == (
        pytest.approx(second.right()),
        pytest.approx(second.right() + gap),
    )
    assert reference.y1 == reference.y2
    assert mine.y1 == mine.y2


def test_an_equal_gap_can_be_kept_on_the_left_too():
    gap = 0.4 * W
    first, second, _ = three_card(0)
    moving = card(first.left() - gap - W - 4, 0)
    result = snap(moving, [first, second], 8)
    assert moving.right() + result.dx == pytest.approx(first.left() - gap)


def test_a_card_in_another_row_gives_no_gap():
    gap = 0.4 * W
    first = card(0, 0)
    second = card(W + gap, 1000)  # Far below: not in the moving card's row
    moving = card(2 * W + 2 * gap + 3, 0)
    result = snap(moving, [first, second], 8)
    assert result.dx == 0


def test_an_equal_gap_snaps_on_the_y_axis_in_a_column():
    gap = 30.0
    first = card(0, 0)
    second = card(0, H + gap)
    moving = card(2, 2 * H + 2 * gap - 5)
    result = snap(moving, [first, second], 8)
    assert moving.top() + result.dy == pytest.approx(second.bottom() + gap)
    assert all(guide.x1 == guide.x2 for guide in result.y_guides)


# Edges


def far_below(x, w=W):
    """A card well below the other, so only the x axis can snap, and a different width so the
    centres don't line up with the edges."""
    return card(x, 1000, w=w)


def test_left_edge_to_left_edge():
    result = snap(far_below(503, w=60), [card(500, 0)], 8)
    assert result.dx == pytest.approx(-3)


def test_right_edge_to_right_edge():
    moving = far_below(500 + W - 60 + 3, w=60)
    result = snap(moving, [card(500, 0)], 8)
    assert moving.right() + result.dx == pytest.approx(500 + W)


def test_left_edge_to_right_edge():
    moving = far_below(500 + W + 4, w=60)
    result = snap(moving, [card(500, 0)], 8)
    assert moving.left() + result.dx == pytest.approx(500 + W)


def test_right_edge_to_left_edge():
    moving = far_below(500 - 60 - 4, w=60)
    result = snap(moving, [card(500, 0)], 8)
    assert moving.right() + result.dx == pytest.approx(500)


def test_top_edge_to_bottom_edge():
    moving = card(1000, H + 5, h=90)
    result = snap(moving, [card(0, 0)], 8)
    assert moving.top() + result.dy == pytest.approx(H)


def test_bottom_edge_to_top_edge():
    moving = card(1000, -90 - 5, h=90)
    result = snap(moving, [card(0, 0)], 8)
    assert moving.bottom() + result.dy == pytest.approx(0)


def test_top_to_top_and_bottom_to_bottom():
    top = snap(card(1000, 4, h=90), [card(0, 0)], 8)
    assert top.dy == pytest.approx(-4)
    bottom = card(1000, H - 90 - 4, h=90)
    assert bottom.bottom() + snap(bottom, [card(0, 0)], 8).dy == pytest.approx(H)


def test_a_turned_cards_edge_is_its_rotated_footprint():
    other = turned(card(500, 0), 30)
    assert other.left() < 500  # The turn widened it
    moving = far_below(other.right() + 5, w=60)
    result = snap(moving, [other], 8)
    assert moving.left() + result.dx == pytest.approx(other.right())


# Midpoint


def test_a_card_snaps_to_the_midpoint_between_two_others():
    a = card(0, 0)
    b = card(400, 300)
    middle = (a.center().x() + b.center().x()) / 2
    moving = card(middle - W / 2 + 4, 2000, w=W)
    # No edge of either card is within reach of the moving card's edges
    result = snap(moving, [a, b], 8)
    assert moving.center().x() + result.dx == pytest.approx(middle)
    (guide,) = result.x_guides
    assert guide.y1 == pytest.approx(0)
    assert guide.y2 == pytest.approx(2000 + H)


def test_a_centre_in_range_beats_a_midpoint():
    a = card(0, 0)
    b = card(16, 600)
    c = card(400, 1200)
    # The moving centre is 5 from a's centre line, 11 from b's, and 3 from their midpoint
    moving = card(5, 2000)
    result = snap(moving, [a, b, c], 8)
    assert moving.center().x() + result.dx == pytest.approx(a.center().x())


# Axes and the empty case


def test_x_and_y_snap_independently():
    result = snap(card(304, 900), [card(300, 0)], 8)
    assert result.dx == pytest.approx(-4)
    assert result.dy == 0
    assert result.x_guides
    assert result.y_guides == ()


def test_both_axes_can_snap_at_once():
    result = snap(card(304, 3), [card(300, 0)], 8)
    assert (result.dx, result.dy) == (pytest.approx(-4), pytest.approx(-3))
    assert result.x_guides and result.y_guides


def test_no_others_means_no_offset_and_no_guides():
    result = snap(card(0, 0), [], 8)
    assert (result.dx, result.dy, result.guides) == (0, 0, ())


def test_guides_are_drawn_against_the_snapped_footprint():
    result = snap(card(304, 900), [card(300, 0)], 8)
    (guide,) = result.x_guides
    assert QPointF(guide.x1, guide.y1) == QPointF(350, 0)


# How a guide is drawn


def test_a_light_gilt_core_takes_a_dark_halo_and_a_dark_one_a_light_halo():
    from PyQt6.QtGui import QColor

    from tarot_canvas.ui.canvas.guides import GUIDE_HALO_ALPHA, halo_for
    from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, GILT_ON_LIGHT

    on_dark = halo_for(QColor(GILT_ON_DARK))
    on_light = halo_for(QColor(GILT_ON_LIGHT))
    assert on_dark.rgb() == QColor("black").rgb()
    assert on_light.rgb() == QColor("white").rgb()
    assert on_dark.alphaF() == pytest.approx(GUIDE_HALO_ALPHA, abs=0.01)


def test_a_line_guide_is_dashed_in_screen_pixels_and_a_gap_is_solid():
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor

    from tarot_canvas.ui.canvas.guides import GUIDE_DASH_PX, guide_pen

    for width in (1.5, 3.5):
        pen = guide_pen(QColor("white"), width, dashed=True)
        assert pen.isCosmetic()
        assert pen.dashPattern()[0] * width == pytest.approx(GUIDE_DASH_PX)
    assert guide_pen(QColor("white"), 1.5, dashed=False).style() == Qt.PenStyle.SolidLine
