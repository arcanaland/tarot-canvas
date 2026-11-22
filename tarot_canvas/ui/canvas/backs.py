from functools import lru_cache

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QPixmap

from tarot_canvas.ui.house_back import HOUSE_EDGE_PX, paint_house_back


def back_path(deck):
    """The deck's default back, or any back it has, or None for the house back"""
    if deck is None:
        return None
    backs, default = deck.get_card_backs()
    if default in backs:
        return backs[default]
    return next(iter(backs.values()), None)


@lru_cache(maxsize=16)
def _house_back(w, h):
    """Our custom plum card back"""
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_house_back(painter, w, h, HOUSE_EDGE_PX)
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
