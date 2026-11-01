from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter, QPen, QPixmap, QTextLayout, QTextOption

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.detail import DETAIL_MAX_PX, card_unit_size, detail_level
from tarot_canvas.ui.canvas.selection import LIGHT_GROUND_LUMINANCE, ground_luminance
from tarot_canvas.ui.card_colours import SLOT_COLOUR

# Of the slot's width
CORNER_RADIUS = 0.06
LABEL_MARGIN = 0.06
# Of the slot's height
NUMBER_HEIGHT = 0.28
LABEL_HEIGHT = 0.07

OUTLINE_PX = 1.5
OUTLINE_DARKER = 167  # QColor.darker's factor for 60% of the fill's value
LABEL_LINES = 3


def _label_lines(label, font, width):
    """label wrapped to width, its last line elided if it runs over"""
    layout = QTextLayout(label, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)

    starts = []
    layout.beginLayout()
    while (line := layout.createLine()).isValid():
        line.setLineWidth(width)
        starts.append(line.textStart())
    layout.endLayout()

    ends = [*starts[1:], len(label)]
    lines = [label[start:end].strip() for start, end in zip(starts, ends, strict=True)]
    if len(lines) > LABEL_LINES:
        rest = label[starts[LABEL_LINES - 1] :]
        elided = QFontMetricsF(font).elidedText(rest, Qt.TextElideMode.ElideRight, width)
        lines = [*lines[: LABEL_LINES - 1], elided]
    return lines


def render_slot(number, label, colour, size, scale):
    """A slot's face, size * scale device px"""
    pixmap = QPixmap(size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    width, height = size.width(), size.height()
    fill = QColor(colour)
    on_light = ground_luminance(fill) > LIGHT_GROUND_LUMINANCE
    ink = QColor(Qt.GlobalColor.black if on_light else Qt.GlobalColor.white)

    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    painter.scale(scale, scale)

    painter.setBrush(fill)
    painter.setPen(QPen(fill.darker(OUTLINE_DARKER), OUTLINE_PX))
    inset = OUTLINE_PX / 2
    radius = width * CORNER_RADIUS
    painter.drawRoundedRect(
        QRectF(inset, inset, width - OUTLINE_PX, height - OUTLINE_PX), radius, radius
    )

    painter.setPen(ink)
    number_font = typography.in_pixels(
        typography.font(typography.Role.BODY), height * NUMBER_HEIGHT
    )
    number_font.setBold(True)
    painter.setFont(number_font)
    painter.drawText(QRectF(0, 0, width, height / 2), Qt.AlignmentFlag.AlignCenter, str(number))

    label_font = typography.in_pixels(typography.font(typography.Role.BODY), height * LABEL_HEIGHT)
    painter.setFont(label_font)
    margin = width * LABEL_MARGIN
    text_width = width - 2 * margin
    metrics = QFontMetricsF(label_font)
    for row, line in enumerate(_label_lines(label, label_font, text_width)):
        painter.drawText(
            QRectF(margin, height / 2 + row * metrics.lineSpacing(), text_width, metrics.height()),
            Qt.AlignmentFlag.AlignHCenter,
            line,
        )

    painter.end()
    return pixmap


class SlotItem(DraggableCardItem):
    """A numbered place on the canvas that a card could fill"""

    def __init__(self, number, position_id, parent_tab=None, label="", meaning=""):
        size = card_unit_size()
        face = render_slot(number, label, SLOT_COLOUR, size, 1)
        super().__init__(face, {"id": f"slot:{position_id}"}, parent_tab)
        self.number = number
        self.position_id = position_id
        self.label = label
        self.meaning = meaning
        self._size = size
        self._top_level = DETAIL_MAX_PX // max(size.width(), size.height())

    def mark_colour(self):
        return SLOT_COLOUR

    def set_number(self, number):
        self.number = number
        self._redraw()

    def set_label(self, label):
        self.label = label
        self._redraw()

    def set_reversed(self, reversed):
        """A slot has no reversed."""

    def set_detail(self, device_scale):
        level = detail_level(device_scale, self._top_level)
        if level != self._wanted_level:
            self._wanted_level = level
            self._show_level(level, self._render(level))

    def _render(self, scale):
        return render_slot(self.number, self.label, SLOT_COLOUR, self._size, scale)

    def _redraw(self):
        self._base = self._render(1)
        self._show_level(self._level, self._render(self._level))
