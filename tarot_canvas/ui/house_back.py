from functools import cache
from importlib.resources import files

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

HOUSE_FILL = QColor(58, 36, 48)
HOUSE_EDGE = QColor(140, 112, 80)
HOUSE_EDGE_PX = 3.0
HOUSE_RADIUS = 0.05  # of the card's width
HOUSE_ICON_WIDTH = 0.42  # of the card's width
HOUSE_ICON_ALPHA = 0.45

FILE_ICON_ASPECT = 0.569  # the reference deck's width over height
FILE_ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)


@cache
def _icon():
    return QImage(str(files("tarot_canvas.resources.icons").joinpath("icon.png")))


def _brass_icon(side):
    """The icon at side, as brass where it is light and clear where it is dark"""
    icon = _icon().scaled(
        side,
        side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    tone = QImage(icon.size(), QImage.Format.Format_ARGB32_Premultiplied)
    tone.fill(QColor(0, 0, 0))
    under = QPainter(tone)
    under.drawImage(0, 0, icon)
    under.end()
    brass = QImage(icon.size(), QImage.Format.Format_ARGB32_Premultiplied)
    brass.fill(HOUSE_EDGE)
    brass.setAlphaChannel(tone.convertToFormat(QImage.Format.Format_Grayscale8))
    return brass


def paint_house_back(painter: QPainter, w: int, h: int, edge: float):
    """Our custom plum card back, w by h at the painter's origin, rimmed edge px wide"""
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
    )
    inset = edge / 2.0
    radius = w * HOUSE_RADIUS
    painter.setBrush(HOUSE_FILL)
    painter.setPen(QPen(HOUSE_EDGE, edge))
    painter.drawRoundedRect(QRectF(inset, inset, w - 2 * inset, h - 2 * inset), radius, radius)

    if not _icon().isNull():
        icon = _brass_icon(round(w * HOUSE_ICON_WIDTH))
        painter.setOpacity(HOUSE_ICON_ALPHA)
        painter.drawImage(QPointF((w - icon.width()) / 2.0, (h - icon.height()) / 2.0), icon)


def file_icon(size: int) -> QImage:
    """The house back standing in a size-px square, as the icon of a .tarotdeck file"""
    w = round(size * FILE_ICON_ASPECT)
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.translate((size - w) // 2, 0)
    paint_house_back(painter, w, size, max(1.0, HOUSE_EDGE_PX * size / 256))
    painter.end()
    return image
