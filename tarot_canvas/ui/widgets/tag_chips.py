from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from tarot_canvas.ui.library import units

CHIP_PADDING_H = units.LARGE_SPACING
CHIP_PADDING_V = units.SMALL_SPACING
CHIP_SPACING = units.SMALL_SPACING
CHIP_RADIUS = units.COVER_RADIUS


def normalized_tags(value):
    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list | tuple):
        return ()

    return tuple(text for text in (str(tag).strip() for tag in value) if text)


class TagChips(QWidget):
    """One chip per tag."""

    def __init__(self, tags, measure, parent=None):
        super().__init__(parent)
        self.tags = tuple(tags)
        self._measure = max(1, measure)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.setAccessibleName(", ".join(self.tags))

    # -- geometry ---------------------------------------------------------

    def chip_height(self):
        return QFontMetrics(self.font()).height() + 2 * CHIP_PADDING_V

    def rows(self, width):
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
                # Half-pixel inset so the 1px stroke lands on the pixel
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
