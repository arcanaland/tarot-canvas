from datetime import UTC, datetime

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor

from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.ui.canvas import tab_icon
from tarot_canvas.ui.canvas.tab_icon import (
    MINIMAP,
    Mark,
    layout_marks,
    reading_marks,
    snapped,
    spread_icon,
)
from tarot_canvas.ui.card_colours import CARD_COLOURS


def card(x, y, angle=0.0, colour=CARD_COLOURS["cups"], z=0.0, w=100.0, h=160.0):
    return (x, y, w, h, angle, colour, z)


def test_a_mark_keeps_its_number_when_z_reorders_it():
    raw = (
        (*card(0, 0, z=2), 1),
        (*card(150, 0, z=0), 2),
        (*card(300, 0, z=1), 3),
    )

    assert [mark.number for mark in layout_marks(raw)] == [2, 3, 1]
    assert [mark.number for mark in snapped(layout_marks(raw))] == [2, 3, 1]


def test_a_card_mark_has_no_number():
    assert layout_marks((card(0, 0),))[0].number is None


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
    marks = snapped(layout_marks((card(0, 0, colour=CARD_COLOURS["wands"]),), MINIMAP.max_fill))
    image = spread_icon(marks).pixmap(QSize(32, 32)).toImage()
    assert image.pixelColor(16, 16) == QColor(CARD_COLOURS["wands"])
    assert image.pixelColor(0, 0).alpha() == 0


def _reading(*card_ids):
    cards = tuple(
        ReadingCard(id=card_id, x=n * 10.0, z=float(len(card_ids) - n))
        for n, card_id in enumerate(card_ids)
    )
    return Reading(date=datetime(2026, 11, 11, tzinfo=UTC), cards=cards)


def test_a_numbered_reading_counts_its_cards_in_order():
    reading = _reading("major_arcana.fool", "minors.cups.ace", "major_arcana.magician")
    raw = reading_marks(reading, QSize(10, 17), numbered=True)
    assert [mark[0] for mark in raw] == [0.0, 10.0, 20.0]
    assert [mark[-1] for mark in raw] == [1, 2, 3]
    # The order is the reading's, not paint order
    assert [mark.number for mark in layout_marks(raw)] == [3, 2, 1]


def test_a_reading_is_unnumbered_by_default():
    reading = _reading("major_arcana.fool", "major_arcana.magician")
    assert all(mark.number is None for mark in layout_marks(reading_marks(reading, QSize(10, 17))))


def test_a_turned_marks_number_is_painted_upright(qapp, monkeypatch):
    painted = []

    def spy(painter, number, w, h, angle):
        transform = painter.worldTransform()
        painted.append((number, angle, transform.m12(), transform.m21()))

    monkeypatch.setattr(tab_icon, "paint_upright_number", spy)
    marks = (Mark(0.5, 0.5, 0.2, 0.35, 90.0, "#ff8800", 0, 4),)
    tab_icon.render_spread(marks, tab_icon.DIAGRAM, 64)

    # The painter isn't turned with the mark; the number is drawn knowing the mark's angle
    assert painted == [(4, 90.0, 0.0, 0.0)]
