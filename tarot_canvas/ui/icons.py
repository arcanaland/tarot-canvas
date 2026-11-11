"""One icon per noun, wherever the noun appears."""

from importlib.resources import files

from tarot_canvas.ui.widgets.placeholder_message import tinted_icon

LIBRARY_ICON = "view-institution"
SPREAD_ICON = "view-grid"
CANVAS_ICON = "draw-rectangle"

DECK_ICON = files("tarot_canvas.resources.icons").joinpath("deck.svg")


def deck_icon():
    """had to draw this one myself in inkscape :3"""
    return tinted_icon(DECK_ICON)
