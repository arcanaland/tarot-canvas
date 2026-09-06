from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from tarot_canvas.ui.canvas.card_item import DraggableCardItem


def test_cards_resample_smoothly(qapp):
    """QGraphicsPixmapItem defaults to FastTransformation, which shears a rotated card.

    Its paint() sets the SmoothPixmapTransform render hint from this mode, overriding
    whatever the view asked for, so the mode has to be set on the item itself.
    """
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    card = DraggableCardItem(pixmap, {"id": "card"})

    assert card.transformationMode() == Qt.TransformationMode.SmoothTransformation
