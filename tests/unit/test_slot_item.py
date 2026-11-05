import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor

from tarot_canvas.ui.canvas.detail import CARD_UNIT_SIZE, card_unit_size, logical_size
from tarot_canvas.ui.canvas.slot_item import render_slot

SIZE = QSize(200, 340)


def colours_in(image, x0, y0, x1, y1):
    return {image.pixelColor(x, y).name() for y in range(y0, y1) for x in range(x0, x1)}


def test_the_unit_is_the_reference_card_as_the_canvas_places_it():
    assert logical_size(QSize(683, 1200)) == CARD_UNIT_SIZE


@pytest.mark.parametrize("installed", [True, False])
def test_the_unit_is_the_same_whatever_is_installed(stub_deck_manager, full_deck, installed):
    stub_deck_manager.get_reference_deck = lambda: full_deck if installed else None
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
