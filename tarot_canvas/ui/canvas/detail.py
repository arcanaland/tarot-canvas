"""Level of detail for card art: each card holds a pixmap sized to how large it is on screen.

A card's logical size never changes. Its pixmap is that size times an integer level, with the
level as its device pixel ratio, so Qt draws it at the same logical size either way. Level 1
is the base the card was placed with; higher levels are decoded from the art file off the GUI
thread and swapped in when they arrive.
"""

import math
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QImageReader, QPixmap

# The largest a card is placed on the canvas, in logical px
CARD_MAX_SIZE = QSize(300, 500)
# No level may be longer than this on its longest side, however large the art
DETAIL_MAX_PX = 4096
# How much of the viewport, either side, counts as on screen for choosing a level
DETAIL_VISIBLE_MARGIN = 0.5
# Wait for zooming and panning to pause before loading anything
DETAIL_SETTLE_MS = 120


def logical_size(source_size):
    """The size a card with art of source_size takes on the canvas: fitted, never enlarged."""
    if (
        source_size.width() <= CARD_MAX_SIZE.width()
        and source_size.height() <= CARD_MAX_SIZE.height()
    ):
        return QSize(source_size)
    return source_size.scaled(CARD_MAX_SIZE, Qt.AspectRatioMode.KeepAspectRatio)


def top_level(source_size, logical):
    """The highest level worth building: enough to show every pixel of the art."""
    if logical.isEmpty():
        return 1
    ratio = max(
        source_size.width() / logical.width(),
        source_size.height() / logical.height(),
    )
    ceiling = DETAIL_MAX_PX // max(logical.width(), logical.height())
    return max(1, min(math.ceil(ratio - 1e-9), ceiling))


def detail_level(device_scale, highest):
    """The smallest level that is never magnified at device_scale device px per logical px.

    Rounding up keeps each draw a minification of under 2x, which bilinear filtering handles
    without the shimmer a larger reduction gets under drift.
    """
    return max(1, min(highest, math.ceil(device_scale - 1e-9)))


def read_art(path, size=None):
    """Decode the art at path, at size if given."""
    reader = QImageReader(path)
    source = reader.size()
    if size is not None and source.isValid() and size.width() < source.width():
        reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        return image
    if size is not None and image.size() != size:
        image = image.scaled(
            size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    return image


def load_card_art(path):
    """(base pixmap, source size) for a card's art, or None if it can't be read."""
    source = QImageReader(path).size()
    if not source.isValid():
        image = read_art(path)
        if image.isNull():
            return None
        source = image.size()
        image = image.scaled(
            logical_size(source),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    else:
        image = read_art(path, logical_size(source))
        if image.isNull():
            return None
    return QPixmap.fromImage(image), source


class _Decode(QRunnable):
    def __init__(self, loader, ticket, path, size):
        super().__init__()
        self._loader = loader
        self._ticket = ticket
        self._path = path
        self._size = size

    def run(self):
        image = read_art(self._path, self._size)
        self._loader.decoded.emit(self._ticket, image)


class ArtLoader(QObject):
    """Decodes art on the thread pool and hands each image back on the GUI thread."""

    decoded = pyqtSignal(int, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._next_ticket = 0
        self._waiting = {}
        self.decoded.connect(self._deliver)

    def request(self, card, path, size, level):
        self._next_ticket += 1
        ticket = self._next_ticket
        self._waiting[ticket] = (weakref.ref(card), level)
        QThreadPool.globalInstance().start(_Decode(self, ticket, path, size))

    @pyqtSlot(int, QImage)  # a slot of this object, so a decode lands on the GUI thread
    def _deliver(self, ticket, image):
        ref, level = self._waiting.pop(ticket, (None, None))
        card = ref() if ref is not None else None
        if card is None or sip.isdeleted(card) or image.isNull():
            return
        card.receive_detail(level, image)


_loader = None


def art_loader():
    """The one loader, created on first use on the GUI thread."""
    global _loader
    if _loader is None:
        _loader = ArtLoader()
    return _loader
