import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor

from tarot_canvas.ui.canvas.tab_icon import MINIMAP, layout_marks, snapped, spread_icon
from tarot_canvas.ui.card_colours import CARD_COLOURS


def card(x, y, angle=0.0, colour_key="cups", z=0.0, w=100.0, h=160.0):
    return (x, y, w, h, angle, colour_key, z)


def test_an_empty_canvas_has_no_marks():
    assert layout_marks(()) == ()


def test_one_card_is_centred_and_capped():
    (mark,) = layout_marks((card(500, -300),), max_fill=0.6)
    assert (mark.x, mark.y) == pytest.approx((0.5, 0.5))
    assert mark.h == pytest.approx(0.6)
    assert mark.w == pytest.approx(0.6 * 100 / 160)


def test_a_line_keeps_its_aspect():
    marks = layout_marks((card(0, 0), card(150, 0), card(300, 0)))
    assert len({m.y for m in marks}) == 1
    assert marks[0].y == pytest.approx(0.5)
    xs = [m.x for m in marks]
    assert xs[1] - xs[0] == pytest.approx(xs[2] - xs[1])
    assert xs[1] == pytest.approx(0.5)
    assert marks[0].w == pytest.approx(marks[0].h * 100 / 160)


def test_marks_are_in_ascending_z():
    marks = layout_marks((card(0, 0, z=3), card(50, 0, z=1), card(100, 0, z=2)))
    assert [m.z for m in marks] == [1, 2, 3]


def test_a_turned_card_keeps_its_angle():
    marks = layout_marks((card(0, 0), card(150, 0, angle=90.0)))
    assert [m.angle for m in marks] == [0.0, 90.0]


def test_a_small_move_snaps_equal():
    spread = (card(0, 0), card(150, 0), card(300, 40))
    nudged = (card(0, 0), card(151, 0), card(300, 40))
    assert snapped(layout_marks(spread)) == snapped(layout_marks(nudged))


def test_moving_the_whole_spread_changes_nothing():
    spread = (card(0, 0), card(150, 0, angle=90.0), card(300, 40))
    moved = tuple(card(x + 2000, y - 700, angle) for x, y, _, _, angle, _, _ in spread)
    assert snapped(layout_marks(spread)) == snapped(layout_marks(moved))


def test_one_card_paints_its_colour_on_the_ground(qapp):
    marks = snapped(layout_marks((card(0, 0, colour_key="wands"),), MINIMAP.max_fill))
    image = spread_icon(marks).pixmap(QSize(32, 32)).toImage()
    assert image.pixelColor(16, 16) == QColor(CARD_COLOURS["wands"])
    assert image.pixelColor(0, 0).alpha() == 0
