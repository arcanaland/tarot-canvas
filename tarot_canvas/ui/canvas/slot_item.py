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


def slot_ink(fill):
    """Black or white, whichever reads on fill"""
    on_light = ground_luminance(fill) > LIGHT_GROUND_LUMINANCE
    return QColor(Qt.GlobalColor.black if on_light else Qt.GlobalColor.white)


def paint_number(painter, number, rect):
    """number in the top half of a slot filling rect, in the painter's pen"""
    font = typography.in_pixels(
        typography.font(typography.Role.BODY), rect.height() * NUMBER_HEIGHT
    )
    font.setBold(True)
    painter.setFont(font)
    top_half = QRectF(rect.x(), rect.y(), rect.width(), rect.height() / 2)
    painter.drawText(top_half, Qt.AlignmentFlag.AlignCenter, str(number))


def _paint_landscape_text(painter, number, label, rect, basis):
    """number beside label across a wide rect, at the sizes a slot basis px tall uses"""
    font = typography.in_pixels(typography.font(typography.Role.BODY), basis * NUMBER_HEIGHT)
    font.setBold(True)
    painter.setFont(font)
    number_width = QFontMetricsF(font).horizontalAdvance(str(number))
    margin = rect.height() * LABEL_MARGIN
    gap = margin * 2
    label_font = typography.in_pixels(typography.font(typography.Role.BODY), basis * LABEL_HEIGHT)
    metrics = QFontMetricsF(label_font)
    text_width = rect.width() - number_width - gap - 2 * margin
    lines = _label_lines(label, label_font, text_width) if label else []
    # The pair centred together, the number's column first
    widest = max((metrics.horizontalAdvance(line) for line in lines), default=0.0)
    left = rect.x() + (rect.width() - (number_width + (gap + widest if lines else 0.0))) / 2
    painter.drawText(
        QRectF(left, rect.y(), number_width, rect.height()),
        Qt.AlignmentFlag.AlignCenter,
        str(number),
    )
    painter.setFont(label_font)
    top = rect.y() + (rect.height() - len(lines) * metrics.lineSpacing()) / 2
    for row, line in enumerate(lines):
        painter.drawText(
            QRectF(
                left + number_width + gap,
                top + row * metrics.lineSpacing(),
                widest,
                metrics.height(),
            ),
            Qt.AlignmentFlag.AlignLeft,
            line,
        )


def render_slot(number, label, colour, size, scale, edge=None, ink=None, dashed=False, text_turn=0):
    """A slot's face, size * scale device px. edge and ink default to the fill's darker outline and
    whichever of black or white reads on it; dashed draws the outline dashed. text_turn, a multiple of
    90, turns the text back by that much, so a slot lying turned reads upright: across, on a slot
    lying on its side"""
    pixmap = QPixmap(size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    width, height = size.width(), size.height()
    fill = QColor(colour)

    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    painter.scale(scale, scale)

    painter.setBrush(fill)
    outline = QPen(QColor(edge) if edge is not None else fill.darker(OUTLINE_DARKER), OUTLINE_PX)
    if dashed:
        outline.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(outline)
    inset = OUTLINE_PX / 2
    radius = width * CORNER_RADIUS
    painter.drawRoundedRect(
        QRectF(inset, inset, width - OUTLINE_PX, height - OUTLINE_PX), radius, radius
    )

    painter.setPen(QColor(ink) if ink is not None else slot_ink(fill))
    turn = text_turn % 360
    if turn:
        painter.translate(width / 2, height / 2)
        painter.rotate(-turn)
        if turn % 180:
            _paint_landscape_text(
                painter, number, label, QRectF(-height / 2, -width / 2, height, width), height
            )
            painter.end()
            return pixmap
        painter.translate(-width / 2, -height / 2)
    paint_number(painter, number, QRectF(0, 0, width, height))

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
