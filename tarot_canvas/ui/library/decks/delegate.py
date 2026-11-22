from dataclasses import dataclass

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOption

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.catalog.downloads import DeckState
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.covers.ghost import paint_emblem, paint_ghost_cover, paint_placeholder_well
from tarot_canvas.ui.library.decks.model import ExpandedRole, HandmadeRole, ProgressRole, StateRole
from tarot_canvas.ui.library.roles import (
    SELECTED_SUBTITLE_ALPHA,
    CoverPathRole,
    SubtitleRole,
)
from tarot_canvas.ui.library.section_row import is_section

HOVER_ALPHA = 38  # ~15% Highlight behind a hovered cell
TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
SECTION_SPACE = 2 * units.GRID_UNIT
HEADING_RULE_ALPHA = 51


@dataclass(frozen=True)
class CellLayout:
    cover: QRect
    title: QRect
    subtitle: QRect


class DeckDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, density=units.DENSITY_MEDIUM, cover_cache=None):
        super().__init__(parent)
        self._cover_cache = cover_cache or CoverCache()
        self._density = density

    @property
    def density(self):
        return self._density

    def set_density(self, density):
        if density not in units.DENSITIES:
            density = units.DENSITY_MEDIUM
        if density == self._density:
            return False
        self._density = density
        return True

    def cover_size(self):
        return QSize(*units.cover_size(self._density))

    # -- fonts ------------------------------------------------------------

    def title_font(self, base=None, selected=False):
        font = QFont(base or QApplication.font())
        # The HIG asks for bold only on the selected item
        font.setBold(selected)
        return font

    def subtitle_font(self):
        return typography.font(typography.Role.SMALL)

    @staticmethod
    def heading_font():
        return typography.font(typography.Role.HEADING_2)

    # -- geometry ---------------------------------------------------------

    def line_width(self, option):
        view = self.parent()
        if view is None:
            return 1
        return max(1, view.viewport().width() - 2 * view.spacing())

    def heading_layout(self, rect, row):
        """(text line, rule) inside a heading's rect"""
        space = SECTION_SPACE if row > 0 else 0
        line_height = QFontMetrics(self.heading_font()).height()
        text = QRect(rect.left(), rect.top() + space, rect.width(), line_height)
        rule = QRect(rect.left(), text.bottom() + 1 + units.SMALL_SPACING, rect.width(), 1)
        return text, rule

    def heading_size(self, option, row):
        _, rule = self.heading_layout(QRect(0, 0, self.line_width(option), 0), row)
        return QSize(rule.width(), rule.bottom() + 1)

    def _layout(self, option):
        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        subtitle_height = QFontMetrics(self.subtitle_font()).height()

        content_left = option.rect.left() + units.LARGE_SPACING
        content_width = max(1, option.rect.width() - 2 * units.LARGE_SPACING)
        top = option.rect.top() + units.LARGE_SPACING

        cover_rect = QRect(content_left, top, content_width, cover.height())
        title_top = cover_rect.bottom() + 1 + units.SMALL_SPACING
        title_rect = QRect(content_left, title_top, content_width, title_height)
        subtitle_rect = QRect(content_left, title_rect.bottom() + 1, content_width, subtitle_height)
        return CellLayout(cover=cover_rect, title=title_rect, subtitle=subtitle_rect)

    def sizeHint(self, option, index):
        if is_section(index):
            return self.heading_size(option, index.row())
        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        subtitle_height = QFontMetrics(self.subtitle_font()).height()
        return QSize(
            cover.width() + 2 * units.LARGE_SPACING,
            cover.height()
            + title_height
            + subtitle_height
            + units.SMALL_SPACING
            + 2 * units.LARGE_SPACING,
        )

    # -- painting ---------------------------------------------------------

    def paint(self, painter, option, index):
        if is_section(index):
            self._paint_shelf(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        self._paint_background(painter, option, palette, selected, hovered)

        layout = self._layout(option)
        self._paint_cover(painter, layout.cover, palette, index, selected)

        title_colour = palette.highlightedText().color() if selected else palette.text().color()
        self._paint_line(
            painter,
            layout.title,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
            self.title_font(option.font, selected=selected),
            title_colour,
        )
        self._paint_subtitle(painter, layout.subtitle, palette, index, selected)

        painter.restore()

    @staticmethod
    def line_palette(option):
        palette = QPalette(option.palette)
        active = bool(option.state & QStyle.StateFlag.State_Active)
        palette.setCurrentColorGroup(
            QPalette.ColorGroup.Active if active else QPalette.ColorGroup.Inactive
        )
        return palette

    def _paint_shelf(self, painter, option, index):
        painter.save()
        palette = self.line_palette(option)
        colour = palette.text().color()
        line, rule = self.heading_layout(option.rect, index.row())
        font = self.heading_font()
        # A cell's padding, so the text starts where the cover's content does
        text_rect = line.adjusted(units.LARGE_SPACING, 0, -units.LARGE_SPACING, 0)
        expanded = index.data(ExpandedRole)
        if expanded is not None:
            engaged = QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus
            font.setUnderline(bool(option.state & engaged))
            self._paint_arrow(painter, option, line, expanded, palette)
            indent = line.height() + units.SMALL_SPACING
            if option.direction == Qt.LayoutDirection.RightToLeft:
                text_rect.setRight(line.right() - indent)
            else:
                text_rect.setLeft(line.left() + indent)
        self._paint_heading(painter, text_rect, rule, index.data() or "", font, colour)
        painter.restore()

    @staticmethod
    def _paint_arrow(painter, option, line, expanded, palette):
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        arrow = QStyleOption()
        arrow.state = QStyle.StateFlag.State_Enabled
        arrow.palette = palette
        arrow.rect = QRect(line.left(), line.top(), line.height(), line.height())
        if rtl:
            arrow.rect.moveRight(line.right())
        if expanded:
            element = QStyle.PrimitiveElement.PE_IndicatorArrowDown
        elif rtl:
            element = QStyle.PrimitiveElement.PE_IndicatorArrowLeft
        else:
            element = QStyle.PrimitiveElement.PE_IndicatorArrowRight
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawPrimitive(element, arrow, painter, option.widget)

    @staticmethod
    def _paint_heading(painter, text_rect, rule, text, font, colour):
        """The text as drawn, which may be elided"""
        painter.setFont(font)
        painter.setPen(colour)
        elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, int(TEXT_FLAGS), elided)
        rule_colour = QColor(colour)
        rule_colour.setAlpha(HEADING_RULE_ALPHA)
        painter.fillRect(rule, rule_colour)
        return elided

    def _paint_subtitle(self, painter, rect, palette, index, selected):
        if selected:
            subtitle_colour = QColor(palette.highlightedText().color())
            subtitle_colour.setAlpha(SELECTED_SUBTITLE_ALPHA)
        else:
            subtitle_colour = palette.placeholderText().color()
        self._paint_line(
            painter,
            rect,
            index.data(SubtitleRole) or "",
            self.subtitle_font(),
            subtitle_colour,
        )

    def _paint_background(self, painter, option, palette, selected, hovered):
        if not (selected or hovered):
            return
        colour = QColor(palette.highlight().color())
        if not selected:
            colour.setAlpha(HOVER_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(option.rect, units.CORNER_RADIUS, units.CORNER_RADIUS)

    def _paint_cover(self, painter, well, palette, index, selected=False):
        pixmap = None
        path = index.data(CoverPathRole)
        if path:
            pixmap = self._cover_cache.get(
                path, self.cover_size(), painter.device().devicePixelRatioF()
            )

        state = index.data(StateRole)
        ghost = state is not None and state is not DeckState.INSTALLED

        if pixmap is None:
            paint_placeholder_well(painter, well, palette)
            if ghost:
                self._paint_ghost(painter, well, QPixmap(), index, state, palette)
            self._paint_handmade(painter, well, palette, index)
            return

        art = self._art_rect(well, pixmap)

        # not installed
        if ghost:
            self._paint_ghost(painter, art, pixmap, index, state, palette, dimmed=not selected)
        else:
            painter.drawPixmap(art.topLeft(), pixmap)

        self._paint_cover_border(painter, art, palette)
        self._paint_handmade(painter, art, palette, index)

    @staticmethod
    def _paint_handmade(painter, cover, palette, index):
        """A deck made here"""
        if index.data(HandmadeRole):
            paint_emblem(painter, cover, QIcon.fromTheme("document-edit"), palette)

    @staticmethod
    def _art_rect(well, pixmap):
        """Where pixmap goes in the well, in logical px"""
        art = QRect(
            0,
            0,
            round(pixmap.width() / pixmap.devicePixelRatio()),
            round(pixmap.height() / pixmap.devicePixelRatio()),
        )

        # Bottom-aligned inside the well, so titles sit the same distance under
        # the artwork whatever aspect ratio the deck's cards happen to be.
        art.moveCenter(well.center())
        art.moveBottom(well.bottom())
        return art

    @staticmethod
    def _paint_cover_border(painter, art, palette):
        border = QColor(palette.text().color())
        border.setAlpha(units.COVER_BORDER_ALPHA)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border)
        painter.drawRoundedRect(art, units.COVER_RADIUS, units.COVER_RADIUS)

    @staticmethod
    def _paint_ghost(painter, rect, pixmap, index, state, palette, dimmed=True):
        """A deck not installed yet"""
        downloading = state is DeckState.DOWNLOADING
        paint_ghost_cover(
            painter,
            rect,
            pixmap,
            progress=(index.data(ProgressRole) or 0.0) if downloading else None,
            failed=state is DeckState.FAILED,
            emblem=QIcon.fromTheme("download"),
            palette=palette,
            ground=palette.base().color(),  # the view's, under an unselected tile
            dimmed=dimmed,
        )

    @staticmethod
    def _paint_line(painter, rect, text, font, colour):
        painter.setFont(font)
        painter.setPen(colour)
        elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), elided
        )
