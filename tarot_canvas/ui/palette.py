from PyQt6.QtGui import QColor, QPalette

MUTED_TEXT_OPACITY = 0.75

# WindowText alphas
SUBTLE_FILL_ALPHA = 0.04
GHOST_BAR_ALPHA = 0.10

# Highlight alpha behind an inline message
MESSAGE_FILL_ALPHA = 0.20

# Breeze's warning yellow, in place of Highlight for a warning
WARNING_COLOUR = QColor("#fdbc4b")


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


def _message_accent(palette, warning):
    return WARNING_COLOUR if warning else palette.color(QPalette.ColorRole.Highlight)


def message_fill(palette, warning=False):
    """The background of an inline message: its accent, faint over Window."""
    return blend(
        _message_accent(palette, warning),
        palette.color(QPalette.ColorRole.Window),
        MESSAGE_FILL_ALPHA,
    )


def message_border(palette, warning=False):
    return _message_accent(palette, warning)
