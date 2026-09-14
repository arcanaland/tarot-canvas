"""Silhouettes an esoterica tab would show if it had any data"""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetricsF, QImage, QLinearGradient, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from tarot_canvas.ui.palette import ghost_bar, subtle_fill
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    BODY_LINE_HEIGHT,
    CORNER_RADIUS,
    HEADING_TO_BODY,
    PADDING,
    PASSAGE_SPACING,
    SIDE_MARGIN,
    TITLE_PIXEL_SIZE,
    TITLE_TO_AUTHOR,
    TOP_MARGIN,
    column_width,
)

BAR_HEIGHT = 0.6  # of the font height of the line a bar stands in for

# Fractions of the inner width, fixed so screenshots and tests stay stable
TITLE_WIDTH = 0.40
AUTHOR_WIDTH = 0.25
BODY_WIDTHS = (1.0, 1.0, 0.92, 0.60)


def ghost_layout(font, width):
    title_font = QFont(font)
    title_font.setPixelSize(TITLE_PIXEL_SIZE)
    title_font.setBold(True)
    title = QFontMetricsF(title_font).height()
    body = QFontMetricsF(font).height()

    # (width fraction, line height, text height, gap after)
    lines = [
        (TITLE_WIDTH, title, title, TITLE_TO_AUTHOR),
        (AUTHOR_WIDTH, body, body, HEADING_TO_BODY),
    ]
    lines += [(fraction, body * BODY_LINE_HEIGHT, body, 0) for fraction in BODY_WIDTHS]

    inner = width - 2 * PADDING
    bars, y = [], PADDING
    for fraction, line, text, gap in lines:
        bar = text * BAR_HEIGHT
        bars.append(QRectF(PADDING, y + (line - bar) / 2, inner * fraction, bar))
        y += line + gap
    return bars, y + PADDING


def _paint_ghost(painter, x, y, width, height, bars, palette):
    painter.setBrush(subtle_fill(palette))
    painter.drawRoundedRect(QRectF(x, y, width, height), CORNER_RADIUS, CORNER_RADIUS)

    painter.setBrush(ghost_bar(palette))
    for bar in bars:
        radius = bar.height() / 2
        painter.drawRoundedRect(bar.translated(x, y), radius, radius)


def paint_ghost_passages(painter, rect, palette):
    """Every ghost that in the reading column fading out at the bottom."""
    column = min(rect.width(), column_width(painter.font()))
    width = column - 2 * SIDE_MARGIN
    if width <= 2 * PADDING or rect.height() - 1 <= TOP_MARGIN:
        return

    left = (rect.width() - column) / 2 + SIDE_MARGIN
    bars, height = ghost_layout(painter.font(), width)
    step = height + PASSAGE_SPACING

    dpr = painter.device().devicePixelRatioF()
    layer = QImage(
        round(rect.width() * dpr),
        round(rect.height() * dpr),
        QImage.Format.Format_RGBA64_Premultiplied,
    )
    layer.setDevicePixelRatio(dpr)
    layer.fill(Qt.GlobalColor.transparent)

    layer_painter = QPainter(layer)
    layer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    layer_painter.setPen(Qt.PenStyle.NoPen)
    y = TOP_MARGIN
    while y < rect.height():
        _paint_ghost(layer_painter, left, y, width, height, bars, palette)
        y += step

    # Opaque at the first ghost's top, transparent from the last row's top edge down.
    fade = QLinearGradient(0, TOP_MARGIN, 0, rect.height() - 1)
    fade.setColorAt(0, Qt.GlobalColor.black)
    fade.setColorAt(1, Qt.GlobalColor.transparent)
    layer_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    layer_painter.fillRect(QRectF(0, 0, rect.width(), rect.height()), fade)
    layer_painter.end()

    painter.drawImage(rect.topLeft(), layer)


class GhostPassages(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_ghost_passages(painter, self.rect(), self.palette())
        painter.end()
