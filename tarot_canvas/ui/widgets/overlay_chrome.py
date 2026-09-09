"""Shared painting for chrome that floats over the card artwork.

The KDE HIG asks us twice for what this module provides. Custom styling is to be
avoided and colours are to come from the user's active colour scheme
(hig/simple_by_default.md), yet anything overlaid on the main content area needs
"a contrasting outline around the edge" or it dissolves into a dark scheme
(hig/displaying_content.md). A stylesheet cannot honour both: QSS colours are
literals, and Qt draws a QSS `border-radius` as four edges plus four corner arcs,
so a translucent rim composites twice at every seam and shows bright pips on the
curve. Painting the shape ourselves is one antialiased path with no seams, and it
lets the colours come from the palette.

Window/WindowText rather than Base/Text: this is chrome sitting on top of the
content, not content. Taking both from the same pair is also what keeps the icon
legible -- Breeze tints a symbolic icon to WindowText, so an icon drawn on a
Window-coloured disc always contrasts, in either scheme.
"""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QApplication

# Near-opaque at rest. A more translucent disc looks better over the flat
# background it was first tried on, but card artwork is not flat -- over a busy
# passage the art reads straight through the fill and fights the icon. The rim
# and the hover step are what keep it from looking like a pasted-on sprite.
RESTING_FILL_ALPHA = 0.86
ACTIVE_FILL_ALPHA = 1.0
OUTLINE_ALPHA = 0.5


def _scheme_palette(widget):
    """The colour scheme, not the parent's palette.

    These widgets are children of the image view, so they inherit its palette --
    which a view is free to have recoloured for its own content. Chrome should
    follow the window, so ask the application.
    """
    app = QApplication.instance()
    return app.palette() if app is not None else widget.palette()


def fill_color(widget, active=False):
    color = QColor(_scheme_palette(widget).color(QPalette.ColorRole.Window))
    color.setAlphaF(ACTIVE_FILL_ALPHA if active else RESTING_FILL_ALPHA)
    return color


def outline_color(widget):
    color = QColor(_scheme_palette(widget).color(QPalette.ColorRole.WindowText))
    color.setAlphaF(OUTLINE_ALPHA)
    return color


def text_color(widget):
    """For the icon-less fallback glyph, which needs full contrast, not a rim."""
    return _scheme_palette(widget).color(QPalette.ColorRole.WindowText)


def paint_surface(widget, painter, active=False, radius=None):
    """Fill widget's rect as a rounded, outlined, antialiased surface.

    radius=None means "as round as it goes", i.e. a disc for a square widget.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # A 1px pen straddles the path, so inset by half of it to keep the stroke
    # inside the widget instead of clipped in half at the edge.
    rect = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    if radius is None:
        radius = min(rect.width(), rect.height()) / 2
    painter.setPen(QPen(outline_color(widget), 1.0))
    painter.setBrush(fill_color(widget, active=active))
    painter.drawRoundedRect(rect, radius, radius)
