from dataclasses import dataclass

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_delegate import SELECTED_SUBTITLE_ALPHA, SUBTITLE_SCALE
from tarot_canvas.ui.library.deck_model import CoverPathRole, SubtitleRole
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well
from tarot_canvas.ui.library.notes_model import PreviewRole

THUMBNAIL_ASPECT = 0.57


@dataclass(frozen=True)
class NoteRowLayout:
    well: QRect
    title: QRect
    subtitle: QRect
    preview: QRect


class NoteRowDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, cover_cache=None):
        super().__init__(parent)
        self._cover_cache = cover_cache or CoverCache()

    def _fonts(self, option, selected):
        return (
            units.scaled_font(option.font, bold=selected),
            units.scaled_font(option.font, SUBTITLE_SCALE, bold=False),
        )

    def _line_heights(self, option):
        title, small = self._fonts(option, False)
        return QFontMetrics(title).height(), QFontMetrics(small).height()

    def _layout(self, option):
        title_height, small_height = self._line_heights(option)
        text_height = title_height + 2 * small_height

        top = option.rect.top() + units.LARGE_SPACING
        well = QRect(
            option.rect.left() + units.LARGE_SPACING,
            top,
            max(1, round(text_height * THUMBNAIL_ASPECT)),
            text_height,
        )

        left = well.right() + 1 + units.LARGE_SPACING
        width = max(1, option.rect.right() + 1 - units.LARGE_SPACING - left)
        title = QRect(left, top, width, title_height)
        subtitle = QRect(left, title.bottom() + 1, width, small_height)
        preview = QRect(left, subtitle.bottom() + 1, width, small_height)
        return NoteRowLayout(well=well, title=title, subtitle=subtitle, preview=preview)

    def sizeHint(self, option, index):
        title_height, small_height = self._line_heights(option)
        height = title_height + 2 * small_height
        return QSize(units.GRID_UNIT, height + 2 * units.LARGE_SPACING)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.highlight().color())
            painter.drawRect(option.rect)

        layout = self._layout(option)
        self._paint_thumbnail(painter, layout.well, palette, index.data(CoverPathRole))

        title_font, small_font = self._fonts(option, selected)
        title_colour = palette.highlightedText().color() if selected else palette.text().color()
        _draw(
            painter, layout.title, index.data(Qt.ItemDataRole.DisplayRole), title_font, title_colour
        )

        if selected:
            dim_colour = QColor(palette.highlightedText().color())
            dim_colour.setAlpha(SELECTED_SUBTITLE_ALPHA)
        else:
            dim_colour = palette.placeholderText().color()
        _draw(painter, layout.subtitle, index.data(SubtitleRole), small_font, dim_colour)
        _draw(painter, layout.preview, index.data(PreviewRole), small_font, dim_colour)

        painter.restore()

    def _paint_thumbnail(self, painter, well, palette, path):
        pixmap = None
        if path:
            pixmap = self._cover_cache.get(path, well.size(), painter.device().devicePixelRatioF())

        if pixmap is None:
            # A card the reference deck lacks keeps the same footprint, so no text shifts
            paint_placeholder_well(painter, well, palette)
            return

        art = QRect(
            0,
            0,
            round(pixmap.width() / pixmap.devicePixelRatio()),
            round(pixmap.height() / pixmap.devicePixelRatio()),
        )
        art.moveCenter(well.center())
        painter.drawPixmap(art.topLeft(), pixmap)

        border = QColor(palette.text().color())
        border.setAlpha(units.COVER_BORDER_ALPHA)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border)
        painter.drawRoundedRect(art, units.COVER_RADIUS, units.COVER_RADIUS)


def _draw(painter, rect, text, font, colour):
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        QFontMetrics(font).elidedText(text or "", Qt.TextElideMode.ElideRight, rect.width()),
    )
