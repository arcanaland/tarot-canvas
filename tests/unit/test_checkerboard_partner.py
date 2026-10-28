import math

import pytest
from PyQt6.QtGui import QColor

from tarot_canvas.settings import CHECKERBOARD_COLOR_DEFAULT
from tarot_canvas.ui.canvas.ground import (
    CHECKERBOARD_CONTRAST,
    _decode,
    _to_oklab,
    checkerboard_partner,
)

# Light and dark, saturated and grey, and the colours a tarot canvas is likely to be
COLOURS = {
    "lavender": "#dcd2f0",
    "hot pink": "#ff69b4",
    "solid default": "#1e1432",
    "forest": "#228b22",
    "felt green": "#35654d",
    "yellow": "#ffff00",
    "pure blue": "#0000ff",
    "mid grey": "#808080",
    "near-white": "#fafafa",
    "near-black": "#050505",
    "oxblood": "#4a0000",
    "white": "#ffffff",
    "black": "#000000",
}


def luminance(color):
    """WCAG 2 relative luminance"""

    def linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * linear(color.redF())
        + 0.7152 * linear(color.greenF())
        + 0.0722 * linear(color.blueF())
    )


def contrast(a, b):
    ya, yb = luminance(a), luminance(b)
    return (max(ya, yb) + 0.05) / (min(ya, yb) + 0.05)


def oklch(color):
    lightness, a, b = _to_oklab([_decode(c) for c in (color.redF(), color.greenF(), color.blueF())])
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a))


@pytest.mark.parametrize("hex_colour", COLOURS.values(), ids=COLOURS.keys())
def test_every_partner_sits_at_the_same_contrast(hex_colour):
    colour = QColor(hex_colour)
    partner = checkerboard_partner(colour)

    assert partner.isValid()
    assert contrast(colour, partner) == pytest.approx(CHECKERBOARD_CONTRAST, abs=0.02)


@pytest.mark.parametrize("hex_colour", COLOURS.values(), ids=COLOURS.keys())
def test_a_partner_keeps_the_hue(hex_colour):
    colour = QColor(hex_colour)
    _, chroma, hue = oklch(colour)
    if chroma < 0.02:
        pytest.skip("too grey to have a hue")

    _, _, partner_hue = oklch(checkerboard_partner(colour))

    assert abs((partner_hue - hue + 180) % 360 - 180) < 3


@pytest.mark.parametrize("hex_colour", ["#000000", "#050505", "#808080", "#fafafa", "#ffffff"])
def test_grey_pairs_with_grey(hex_colour):
    partner = checkerboard_partner(QColor(hex_colour))

    assert partner.red() == partner.green() == partner.blue()


@pytest.mark.parametrize(
    ("hex_colour", "darker"),
    [
        ("#dcd2f0", True),
        ("#ffff00", True),
        ("#fafafa", True),
        # Darkening these would crush them toward black, where their hue is lost
        ("#228b22", False),
        ("#4a0000", False),
        ("#1e1432", False),
        ("#000000", False),
    ],
)
def test_light_colours_pair_darker_and_dark_ones_lighter(hex_colour, darker):
    colour = QColor(hex_colour)

    assert (luminance(checkerboard_partner(colour)) < luminance(colour)) is darker


def test_the_default_board_is_two_greys():
    default = QColor(CHECKERBOARD_COLOR_DEFAULT)
    assert default == QColor("#a3a3a3")

    partner = checkerboard_partner(default)

    assert partner.red() == partner.green() == partner.blue()
    assert abs(partner.red() - 139) <= 1
