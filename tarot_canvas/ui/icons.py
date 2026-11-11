"""One icon per noun, wherever the noun appears."""

from importlib.resources import files

from PyQt6.QtGui import QIcon

from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_ESOTERICA,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEW_READINGS,
    LIBRARY_VIEW_SPREADS,
)
from tarot_canvas.ui.widgets.placeholder_message import tinted_icon

LIBRARY_ICON = "view-institution"
SPREAD_ICON = "view-grid"
CANVAS_ICON = "draw-rectangle"

DECK_ICON = files("tarot_canvas.resources.icons").joinpath("deck.svg")
ESOTERICA_VIEW_ICON = files("tarot_canvas.resources.icons").joinpath("esoterica.svg")


def deck_icon():
    """had to draw this one myself in inkscape :3"""
    return tinted_icon(DECK_ICON)


def library_view_icon(view):
    """A Library view's icon, wherever the view is named: its sidebar row, its key"""
    if view == LIBRARY_VIEW_DECKS:
        return deck_icon()
    if view == LIBRARY_VIEW_ESOTERICA:
        # The app's own file, not a theme name
        return tinted_icon(ESOTERICA_VIEW_ICON)
    return QIcon.fromTheme(
        {
            LIBRARY_VIEW_READINGS: "view-calendar-list",
            LIBRARY_VIEW_NOTES: "story-editor",
            LIBRARY_VIEW_SPREADS: SPREAD_ICON,
        }[view]
    )
