from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QApplication

RESTING_FILL_ALPHA = 0.86
ACTIVE_FILL_ALPHA = 1.0
OUTLINE_ALPHA = 0.5


def _scheme_palette(widget):
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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    if radius is None:
        radius = min(rect.width(), rect.height()) / 2
    painter.setPen(QPen(outline_color(widget), 1.0))
    painter.setBrush(fill_color(widget, active=active))
    painter.drawRoundedRect(rect, radius, radius)
