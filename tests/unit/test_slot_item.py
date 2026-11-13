import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor

from tarot_canvas.ui.canvas.detail import CARD_UNIT_SIZE, card_unit_size, logical_size
from tarot_canvas.ui.canvas.slot_item import OUTLINE_DARKER, render_slot, slot_ink

SIZE = QSize(200, 340)


def colours_in(image, x0, y0, x1, y1):
    return {image.pixelColor(x, y).name() for y in range(y0, y1) for x in range(x0, x1)}


def test_the_unit_is_the_reference_card_as_the_canvas_places_it():
    assert logical_size(QSize(683, 1200)) == CARD_UNIT_SIZE


@pytest.mark.parametrize("installed", [True, False])
def test_the_unit_is_the_same_whatever_is_installed(stub_deck_library, full_deck, installed):
    stub_deck_library.reference = lambda: full_deck if installed else None
    assert card_unit_size() == CARD_UNIT_SIZE


@pytest.mark.parametrize("scale", [1, 3])
def test_a_slot_is_the_unit_times_the_scale(qapp, scale):
    assert render_slot(1, "", "#1f77b4", SIZE, scale).size() == SIZE * scale


def test_the_lower_third_is_the_fill(qapp):
    image = render_slot(1, "Present", "#d62728", SIZE, 1).toImage()
    assert image.pixelColor(100, 283) == QColor("#d62728")


def test_a_slots_corners_are_clear(qapp):
    image = render_slot(1, "", "#d62728", SIZE, 1).toImage()
    assert image.pixelColor(0, 0).alpha() == 0


@pytest.mark.parametrize(("fill", "ink"), [("#1f77b4", "#ffffff"), ("#bcbd22", "#000000")])
def test_the_number_reads_against_its_fill(qapp, fill, ink):
    image = render_slot(8, "", fill, SIZE, 1).toImage()
    assert ink in colours_in(image, 40, 40, 160, 130)


def test_a_long_label_stops_at_three_lines(qapp):
    short = render_slot(1, "word " * 3, "#d62728", SIZE, 1).toImage()
    long = render_slot(1, "word " * 200, "#d62728", SIZE, 1).toImage()
    below_three_lines = (20, 280, 180, 330)
    assert colours_in(short, *below_three_lines) == {"#d62728"}
    assert colours_in(long, *below_three_lines) == {"#d62728"}
    assert long != short


def test_a_slots_options_left_out_draw_the_designers_slot(qapp):
    """The edge, ink, dash and turn a reading's socket asks for change nothing by default"""
    fill = QColor("#5a5a5a")
    plain = render_slot(4, "Hopes and Fears", fill, SIZE, 2).toImage()
    spelled_out = render_slot(
        4,
        "Hopes and Fears",
        fill,
        SIZE,
        2,
        edge=fill.darker(OUTLINE_DARKER),
        ink=slot_ink(fill),
        dashed=False,
        text_turn=0,
    ).toImage()

    assert plain == spelled_out
    for option in ({"dashed": True}, {"text_turn": 90}, {"ink": "#ff0000"}, {"edge": "#00ff00"}):
        assert render_slot(4, "Hopes and Fears", fill, SIZE, 2, **option).toImage() != plain


def test_a_slot_turned_a_full_turn_reads_as_one_not_turned(qapp):
    plain = render_slot(2, "Obstacle", "#5a5a5a", SIZE, 1).toImage()
    assert render_slot(2, "Obstacle", "#5a5a5a", SIZE, 1, text_turn=360).toImage() == plain
