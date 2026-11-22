"""A heading row in a Library list, grouping the rows below it by where they came from"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QStyle

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.library.roles import SectionRole, ToggleRole
from tarot_canvas.ui.library.row_delegate import IconRowDelegate


def is_section(index):
    return bool(index.data(SectionRole))


def is_toggle(index):
    return bool(index.data(ToggleRole))


def section_font():
    font = typography.font(typography.Role.SMALL)
    font.setBold(True)
    return font


def section_size_hint():
    # One line of the heading, a gap above it to part it from the section before
    height = QFontMetrics(section_font()).height() + units.LARGE_SPACING + units.SMALL_SPACING
    return QSize(units.GRID_UNIT, height)


def paint_section(painter, option, index):
    painter.save()
    font = section_font()
    rect = option.rect.adjusted(units.LARGE_SPACING, 0, -units.LARGE_SPACING, 0)
    text = index.data(Qt.ItemDataRole.DisplayRole) or ""
    painter.setFont(font)
    painter.setPen(option.palette.placeholderText().color())
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
        QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width()),
    )
    painter.restore()


def toggle_size_hint():
    return QSize(
        units.GRID_UNIT,
        QFontMetrics(typography.font(typography.Role.SMALL)).height() + 2 * units.LARGE_SPACING,
    )


def paint_toggle(painter, option, index):
    """A quiet row of small text that acts when clicked, as a link would"""
    painter.save()
    font = typography.font(typography.Role.SMALL)
    hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
    focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
    font.setUnderline(hovered or focused)
    rect = option.rect.adjusted(units.LARGE_SPACING, 0, -units.LARGE_SPACING, 0)
    painter.setFont(font)
    painter.setPen(option.palette.placeholderText().color())
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        QFontMetrics(font).elidedText(
            index.data(Qt.ItemDataRole.DisplayRole) or "", Qt.TextElideMode.ElideRight, rect.width()
        ),
    )
    painter.restore()


class SectionedRowDelegate(IconRowDelegate):
    """An icon row, or the heading of a section of them"""

    def sizeHint(self, option, index):
        if is_section(index):
            return section_size_hint()
        if is_toggle(index):
            return toggle_size_hint()
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        if is_section(index):
            paint_section(painter, option, index)
            return
        if is_toggle(index):
            paint_toggle(painter, option, index)
            return
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if is_section(index) or is_toggle(index):
            return False
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        if is_section(index) or is_toggle(index):
            return False
        return super().helpEvent(event, view, option, index)
