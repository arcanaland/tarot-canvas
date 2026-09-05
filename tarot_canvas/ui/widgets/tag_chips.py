"""Deck tags, drawn as chips rather than as a comma-joined sentence.

`DECK.md` defines `[deck].tags` as "free-vocabulary categorization tags. No registry, no
behavior" — human vocabulary, not machine identifiers, which is why these are set in the
UI font rather than a monospace one. Chips are what every app that shows tags uses; the
one thing they must not do here is imply a filter that does not exist yet, so they are
drawn flat and are not focusable or clickable.

Colours come from `Button`/`ButtonText`, the pair the scheme already guarantees is legible
together, with a `Mid` outline. The outline is not decoration: under a light scheme Breeze's
`Button` and `Window` differ by about one percent, so a filled chip with no border is
invisible — which is the same failure `hig/displaying_content.md:62` describes for overlays
under a dark scheme, and the same fix.
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from tarot_canvas.ui.library import units

#: Padding inside a chip, either side of its text.
CHIP_PADDING_H = units.LARGE_SPACING

#: Padding above and below the text, applied to each edge.
CHIP_PADDING_V = units.SMALL_SPACING

#: Gap between neighbouring chips, horizontally and between wrapped rows.
CHIP_SPACING = units.SMALL_SPACING

CHIP_RADIUS = units.COVER_RADIUS


def normalized_tags(value):
    """The raw `[deck].tags` value as a tuple of display strings.

    A deck may write a bare string instead of an array, and nothing stops it including
    an empty entry; neither should reach the painter.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple):
        return ()
    return tuple(text for text in (str(tag).strip() for tag in value) if text)


class TagChips(QWidget):
    """One chip per tag, wrapped to the available width."""

    def __init__(self, tags, measure, parent=None):
        super().__init__(parent)
        self.tags = tuple(tags)
        self._measure = max(1, measure)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        # Chips are painted, not laid out as labels, so a screen reader has nothing to
        # read without this (`hig/accessibility.md`, § Screen Reader).
        self.setAccessibleName(", ".join(self.tags))

    # -- geometry ---------------------------------------------------------

    def chip_height(self):
        return QFontMetrics(self.font()).height() + 2 * CHIP_PADDING_V

    def rows(self, width):
        """[[(text, x, width)]] — the chips of each wrapped row, in order.

        The text is elided here rather than at paint time, and only when one tag is
        wider than the whole strip: eliding against the chip's own width instead would
        trim every tag by the pixel or two that `horizontalAdvance` and `elidedText`
        disagree about.
        """
        metrics = QFontMetrics(self.font())
        room = max(0, width - 2 * CHIP_PADDING_H)
        rows, row, pen = [], [], 0
        for tag in self.tags:
            advance = metrics.horizontalAdvance(tag)
            text = tag
            if advance > room:
                text = metrics.elidedText(tag, Qt.TextElideMode.ElideRight, room)
                advance = room
            chip = advance + 2 * CHIP_PADDING_H
            if row and pen + chip > width:
                rows.append(row)
                row, pen = [], 0
            row.append((text, pen, chip))
            pen += chip + CHIP_SPACING
        if row:
            rows.append(row)
        return rows

    def heightForWidth(self, width):
        count = len(self.rows(width))
        if not count:
            return 0
        return count * self.chip_height() + (count - 1) * CHIP_SPACING

    def hasHeightForWidth(self):
        return True

    def sizeHint(self):
        width = self.width() or self._measure
        return QSize(width, self.heightForWidth(width))

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event):
        if not self.tags:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        height = self.chip_height()
        for index, row in enumerate(self.rows(self.width())):
            top = index * (height + CHIP_SPACING)
            for text, x, chip in row:
                painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
                painter.setBrush(self.palette().color(QPalette.ColorRole.Button))
                # Half-pixel inset so the 1px stroke lands on the pixel, not across it.
                painter.drawRoundedRect(
                    QRectF(x + 0.5, top + 0.5, chip - 1, height - 1),
                    CHIP_RADIUS,
                    CHIP_RADIUS,
                )
                painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
                painter.drawText(
                    QRectF(x, top, chip, height),
                    int(Qt.AlignmentFlag.AlignCenter),
                    text,
                )
        painter.end()
