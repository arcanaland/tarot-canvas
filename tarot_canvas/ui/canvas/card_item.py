from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsPixmapItem


class DraggableCardItem(QGraphicsPixmapItem):
    """A card on the playground canvas: draggable, selectable, opens a card view."""

    def __init__(self, pixmap, card_data, parent_tab=None):
        super().__init__(pixmap)
        self.card_data = card_data
        self.parent_tab = parent_tab
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)
        # QGraphicsPixmapItem defaults to FastTransformation, and its paint() sets the
        # SmoothPixmapTransform render hint from this mode — overwriting whatever the
        # view asked for. A rotated card is resampled nearest-neighbour without this,
        # which reads as horizontal shear bands crawling across the face.
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, "open_card_view"):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)
