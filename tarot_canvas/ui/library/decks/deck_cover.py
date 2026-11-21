"""A deck's cover in its header: the art, or an empty well"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QLabel

from tarot_canvas.ui import units
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.covers.ghost import paint_placeholder_well
from tarot_canvas.ui.icons import deck_icon
from tarot_canvas.ui.library.decks.model import deck_cover_path
from tarot_canvas.ui.strings import DECK_VIEW

COLLAPSED_COVER_UNITS = 3


def cover_size(expanded):
    """(width, height) of the cover well."""
    if expanded:
        return units.cover_size(units.DENSITY_SMALL)
    width = COLLAPSED_COVER_UNITS * units.GRID_UNIT
    return width, round(width * units.COVER_ASPECT)


class DeckCover(QLabel):
    def __init__(self, cover_cache=None, parent=None):
        super().__init__(parent)
        self._cache = cover_cache or CoverCache(capacity=8)
        self._path = None
        self._expanded = False
        self.empty = True

    def path(self):
        """The cover art's path, or None"""
        return self._path

    def set_deck(self, deck):
        self.setAccessibleName(DECK_VIEW["cover_of"].format(name=deck.metadata.name))
        self._path = deck_cover_path(deck)
        self._apply()

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        self._apply()

    def _apply(self):
        width, height = cover_size(self._expanded)
        self.setFixedSize(width, height)
        pixmap = self._cache.get(self._path, self.size(), self.devicePixelRatioF())
        self.empty = pixmap is None
        if pixmap is not None:
            self.setPixmap(pixmap)
            self.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
            self.setAccessibleDescription("")
        else:
            self.clear()
            self.setAccessibleDescription(DECK_VIEW["no_cover"])
        self.update()

    def paintEvent(self, event):
        if not self.empty:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_placeholder_well(painter, self.rect(), self.palette(), deck_icon())
        painter.end()
