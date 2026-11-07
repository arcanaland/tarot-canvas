from functools import lru_cache
from importlib.resources import files

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

HOUSE_FILL = QColor(58, 36, 48)
HOUSE_EDGE = QColor(140, 112, 80)
HOUSE_EDGE_PX = 3.0
HOUSE_RADIUS = 0.05  # of the card's width
HOUSE_ICON_WIDTH = 0.42  # of the card's width
HOUSE_ICON_ALPHA = 0.45


def back_path(deck):
    """The deck's default back, or any back it has, or None for the house back"""
    if deck is None:
        return None
    backs, default = deck.get_card_backs()
    if default in backs:
        return backs[default]
    return next(iter(backs.values()), None)


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=16)
def _house_back(w, h):
    """Our custom plum card back"""
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
    )
    inset = HOUSE_EDGE_PX / 2.0
    radius = w * HOUSE_RADIUS
    painter.setBrush(HOUSE_FILL)
    painter.setPen(QPen(HOUSE_EDGE, HOUSE_EDGE_PX))
    painter.drawRoundedRect(QRectF(inset, inset, w - 2 * inset, h - 2 * inset), radius, radius)

    if not _icon().isNull():
        icon = _brass_icon(round(w * HOUSE_ICON_WIDTH))
        painter.setOpacity(HOUSE_ICON_ALPHA)
        painter.drawImage(QPointF((w - icon.width()) / 2.0, (h - icon.height()) / 2.0), icon)
    painter.end()
    return pixmap


def house_back(size: QSize) -> QPixmap:
    """The app's own back at size, drawn once per size"""
    return _house_back(size.width(), size.height())


def back_pixmap(deck, size: QSize) -> tuple[QPixmap, bool]:
    """The deck's back at size, and whether it is the house back"""
    path = back_path(deck)
    if path:
        source = QPixmap(path)
        if not source.isNull():
            scaled = source.scaled(
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            return scaled, False
    return house_back(size), True
