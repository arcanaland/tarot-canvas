from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from tarot_canvas.models.deck_types import Card, CardKind
from tarot_canvas.ui.canvas.card_item import DraggableCardItem


def test_cards_resample_smoothly(qapp):
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    card = DraggableCardItem(
        pixmap, Card(canonical_id="card", kind=CardKind.MAJOR, display_name="card")
    )

    assert card.transformationMode() == Qt.TransformationMode.SmoothTransformation
