from dataclasses import dataclass
from importlib.resources import files

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPalette
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from tarot_canvas.ui import typography
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.coverage_strip import minimum_width, paint_coverage_strip
from tarot_canvas.ui.library.deck_delegate import SELECTED_SUBTITLE_ALPHA
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.esoterica_list_model import (
    CountRole,
    CoverageRole,
    KindRole,
    RowKind,
    TypeRole,
)
from tarot_canvas.ui.widgets.placeholder_message import tinted_icon

GENERIC_ICON = files("tarot_canvas.resources.icons").joinpath("esoterica.svg")

# [meta].type -> a Breeze theme icon.
SOURCE_TYPE_ICONS = {
    "book": "documentation",
    "chapter": "view-readermode",
    "article": "view-pim-news",
    "webpage": "globe-symbolic",
    "manuscript": "document-edit-sign",
    "document": "view-pages-single",
    "tradition": "group",
}

ICON_SIZE = 32
STRIP_WIDTH = minimum_width()
STRIP_HEIGHT_SCALE = 0.6  # of the name's line
# Room for "78"
COUNT_TEXT = "88"


def type_icon(source_type):
    """The icon for a source's [meta].type"""
    name = SOURCE_TYPE_ICONS.get(source_type) if isinstance(source_type, str) else None
    if name is None:
        return tinted_icon(GENERIC_ICON)
    if not QIcon.hasThemeIcon(name):
        return None
    return QIcon.fromTheme(name)


@dataclass(frozen=True)
class SourceRowLayout:
    icon: QRect
    title: QRect
    subtitle: QRect
    strip: QRect  # null when the row is too narrow for it, or has none
    count: QRect  # null without one
    checkbox: QRect  # null without one


def section_font():
    font = typography.font(typography.Role.SMALL)
    font.setBold(True)
    return font


class SourceRowDelegate(QStyledItemDelegate):
    def _fonts(self, option, selected):
        title = QFont(option.font)
        title.setBold(selected)
        return title, typography.font(typography.Role.SMALL)

    def _line_heights(self, option):
        title, small = self._fonts(option, False)
        return QFontMetrics(title).height(), QFontMetrics(small).height()

    def sizeHint(self, option, index):
        if index.data(KindRole) == RowKind.SECTION:
            # One line of the heading, a gap above it to part it from the section before
            font = section_font()
            height = QFontMetrics(font).height() + units.LARGE_SPACING + units.SMALL_SPACING
            return QSize(units.GRID_UNIT, height)
        title_height, small_height = self._line_heights(option)
        height = max(ICON_SIZE, title_height + small_height)
        return QSize(units.GRID_UNIT, height + 2 * units.LARGE_SPACING)

    def _checkbox_size(self, option):
        style = option.widget.style() if option.widget is not None else None
        if style is None:
            return QSize(16, 16)
        return QSize(
            style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, option, option.widget),
            style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, option, option.widget),
        )

    def _layout(self, option, index, selected=False):
        rect = option.rect
        centre_y = rect.center().y()
        title_font, small_font = self._fonts(option, selected)
        title_height, small_height = self._line_heights(option)

        left = rect.left() + units.LARGE_SPACING
        right = rect.right() + 1 - units.LARGE_SPACING

        icon = QRect(left, 0, ICON_SIZE, ICON_SIZE)
        icon.moveCenter(QPoint(icon.center().x(), centre_y))
        text_left = icon.right() + 1 + units.LARGE_SPACING

        checkbox = count = strip = QRect()
        if index.data(KindRole) == RowKind.SOURCE:
            size = self._checkbox_size(option)
            checkbox = QRect(QPoint(right - size.width(), centre_y - size.height() // 2), size)
            count_width = QFontMetrics(title_font).horizontalAdvance(COUNT_TEXT)
            count = QRect(
                checkbox.left() - units.LARGE_SPACING - count_width,
                centre_y - title_height // 2,
                count_width,
                title_height,
            )
            right = count.left() - units.LARGE_SPACING

            # The strip goes before the name has to elide
            strip_left = right - STRIP_WIDTH
            name = index.data(Qt.ItemDataRole.DisplayRole) or ""
            name_width = QFontMetrics(title_font).horizontalAdvance(name)
            if strip_left - units.LARGE_SPACING - text_left >= name_width:
                strip_height = max(2, round(title_height * STRIP_HEIGHT_SCALE))
                strip = QRect(strip_left, centre_y - strip_height // 2, STRIP_WIDTH, strip_height)
                right = strip_left - units.LARGE_SPACING

        width = max(1, right - text_left)
        top = centre_y - (title_height + small_height) // 2
        title = QRect(text_left, top, width, title_height)
        subtitle = QRect(text_left, title.bottom() + 1, width, small_height)
        return SourceRowLayout(icon, title, subtitle, strip, count, checkbox)

    def paint(self, painter, option, index):
        kind = index.data(KindRole)
        if kind == RowKind.SECTION:
            self._paint_section(painter, option, index)
            return

        painter.save()
        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(option.rect, palette.highlight())

        layout = self._layout(option, index, selected)
        title_font, small_font = self._fonts(option, selected)
        text_colour = palette.highlightedText().color() if selected else palette.text().color()
        if selected:
            dim_colour = QColor(palette.highlightedText().color())
            dim_colour.setAlpha(SELECTED_SUBTITLE_ALPHA)
        else:
            dim_colour = palette.placeholderText().color()

        if kind == RowKind.SOURCE:
            icon = type_icon(index.data(TypeRole))
            if icon is not None:
                mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
                icon.paint(painter, layout.icon, Qt.AlignmentFlag.AlignCenter, mode)

        _draw(
            painter, layout.title, index.data(Qt.ItemDataRole.DisplayRole), title_font, text_colour
        )
        _draw(painter, layout.subtitle, index.data(SubtitleRole), small_font, dim_colour)

        if not layout.strip.isNull():
            strip_palette = QPalette(palette)
            strip_palette.setColor(QPalette.ColorRole.Text, text_colour)
            paint_coverage_strip(
                painter,
                layout.strip,
                index.data(CoverageRole),
                strip_palette,
                coloured=not selected,
            )
        if not layout.count.isNull():
            painter.setFont(title_font)
            painter.setPen(text_colour)
            painter.drawText(
                layout.count,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                str(index.data(CountRole)),
            )
        if not layout.checkbox.isNull():
            self._paint_checkbox(painter, option, index, layout.checkbox)

        painter.restore()

    def _paint_section(self, painter, option, index):
        painter.save()
        font = section_font()
        rect = option.rect.adjusted(units.LARGE_SPACING, 0, -units.LARGE_SPACING, 0)
        _draw(
            painter,
            rect,
            index.data(Qt.ItemDataRole.DisplayRole),
            font,
            option.palette.placeholderText().color(),
            Qt.AlignmentFlag.AlignBottom,
        )
        painter.restore()

    def _paint_checkbox(self, painter, option, index, rect):
        box = QStyleOptionViewItem(option)
        box.rect = rect
        box.state = option.state & ~QStyle.StateFlag.State_HasFocus
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        box.state |= QStyle.StateFlag.State_On if checked else QStyle.StateFlag.State_Off
        style = option.widget.style() if option.widget is not None else None
        if style is not None:
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck, box, painter, option.widget
            )

    # -- the checkbox -------------------------------------------------------

    def editorEvent(self, event, model, option, index):
        if index.data(KindRole) != RowKind.SOURCE:
            return False
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            on_box = self._layout(option, index).checkbox.contains(event.position().toPoint())
            if event.button() != Qt.MouseButton.LeftButton or not on_box:
                return False
            if kind == QEvent.Type.MouseButtonRelease:
                _toggle(model, index)
            # Consumed, so a double click on the box doesn't also activate the row
            return True
        if kind == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select):
            _toggle(model, index)
            return True
        return False

    def helpEvent(self, event, view, option, index):
        tooltip = label_for("library.checkbox_tooltip")
        if (
            event.type() == QEvent.Type.ToolTip
            and tooltip
            and index.data(KindRole) == RowKind.SOURCE
            and self._layout(option, index).checkbox.contains(event.pos())
        ):
            QToolTip.showText(event.globalPos(), tooltip, view)
            return True
        return super().helpEvent(event, view, option, index)


def _toggle(model, index):
    checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    new = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
    model.setData(index, new, Qt.ItemDataRole.CheckStateRole)


def _draw(painter, rect, text, font, colour, vertical=Qt.AlignmentFlag.AlignVCenter):
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | vertical),
        QFontMetrics(font).elidedText(text or "", Qt.TextElideMode.ElideRight, rect.width()),
    )
