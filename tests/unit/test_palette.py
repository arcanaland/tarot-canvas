import pytest
from PyQt6.QtGui import QPalette

from tarot_canvas.ui.palette import (
    GHOST_BAR_ALPHA,
    SUBTLE_FILL_ALPHA,
    ghost_bar,
    muted_text,
    subtle_fill,
    with_text_colour,
)

TEXT = QPalette.ColorRole.WindowText
WINDOW = QPalette.ColorRole.Window
CHANNELS = ("red", "green", "blue")


def channels(colour):
    return [getattr(colour, name)() for name in CHANNELS]


def test_muted_text_lies_between_the_text_and_the_window(theme_palette):
    muted = muted_text(theme_palette)

    assert muted.alpha() == 255
    for m, t, w in zip(
        channels(muted),
        channels(theme_palette.color(TEXT)),
        channels(theme_palette.color(WINDOW)),
        strict=True,
    ):
        if t != w:
            assert min(t, w) < m < max(t, w)


def test_muted_text_stays_nearer_the_text(theme_palette):
    """Kirigami's 0.75 is the text's opacity, not the distance towards the window"""
    muted = channels(muted_text(theme_palette))
    text = channels(theme_palette.color(TEXT))
    window = channels(theme_palette.color(WINDOW))

    assert sum(abs(m - t) for m, t in zip(muted, text, strict=True)) < sum(
        abs(m - w) for m, w in zip(muted, window, strict=True)
    )


@pytest.mark.parametrize(
    "role, alpha", [(subtle_fill, SUBTLE_FILL_ALPHA), (ghost_bar, GHOST_BAR_ALPHA)]
)
def test_fills_are_the_text_colour_at_their_alpha(theme_palette, role, alpha):
    colour = role(theme_palette)

    assert channels(colour) == channels(theme_palette.color(TEXT))
    assert colour.alphaF() == pytest.approx(alpha, abs=1 / 255)


def test_with_text_colour_leaves_the_original_alone(theme_palette):
    muted = muted_text(theme_palette)
    original = theme_palette.color(TEXT)

    copy = with_text_colour(theme_palette, muted)

    assert copy.color(TEXT) == muted
    assert theme_palette.color(TEXT) == original
