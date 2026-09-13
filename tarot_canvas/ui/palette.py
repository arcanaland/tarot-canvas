"""Colours derived from a QPalette, so they follow a theme switch.

Pure functions of the palette. A widget calls them with `self.palette()`, and again
on `QEvent.Type.PaletteChange`, which `app.setPalette` delivers.
"""

from PyQt6.QtGui import QColor, QPalette

# Kirigami's Informational placeholder: text at 0.75 opacity over the window
# (PlaceholderMessage.qml:261)
MUTED_TEXT_OPACITY = 0.75

# WindowText alphas; tune by eye, light and dark
SUBTLE_FILL_ALPHA = 0.04
GHOST_BAR_ALPHA = 0.10


def _text(palette):
    return palette.color(QPalette.ColorRole.WindowText)


def blend(over, under, opacity):
    """`over` drawn at `opacity` on `under`, as one opaque colour."""
    return QColor.fromRgbF(
        over.redF() * opacity + under.redF() * (1 - opacity),
        over.greenF() * opacity + under.greenF() * (1 - opacity),
        over.blueF() * opacity + under.blueF() * (1 - opacity),
    )


def with_alpha(colour, alpha):
    colour = QColor(colour)
    colour.setAlphaF(alpha)
    return colour


def muted_text(palette):
    """Secondary text: WindowText at MUTED_TEXT_OPACITY over Window."""
    return blend(_text(palette), palette.color(QPalette.ColorRole.Window), MUTED_TEXT_OPACITY)


def subtle_fill(palette):
    """A panel a shade off the window, such as a passage's background."""
    return with_alpha(_text(palette), SUBTLE_FILL_ALPHA)


def ghost_bar(palette):
    """A silhouette of a line of text, drawn on `subtle_fill`."""
    return with_alpha(_text(palette), GHOST_BAR_ALPHA)


def with_text_colour(palette, colour):
    """A copy of `palette` whose WindowText is `colour`, for a label's setPalette."""
    palette = QPalette(palette)
    palette.setColor(QPalette.ColorRole.WindowText, colour)
    return palette
