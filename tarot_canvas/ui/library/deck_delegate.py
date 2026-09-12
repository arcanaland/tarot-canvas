from dataclasses import dataclass

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_downloads import DeckState
from tarot_canvas.ui.library.deck_model import CoverPathRole, ProgressRole, StateRole, SubtitleRole
from tarot_canvas.ui.library.ghost_paint import paint_ghost_cover, paint_placeholder_well

HOVER_ALPHA = 38  # ~15% Highlight behind a hovered cell
SELECTED_SUBTITLE_ALPHA = 200

SUBTITLE_SCALE = 0.85


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

    def subtitle_font(self, base=None):
        font = QFont(base or QApplication.font())
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * SUBTITLE_SCALE)
        else:
            font.setPixelSize(max(1, round(font.pixelSize() * SUBTITLE_SCALE)))
        font.setBold(False)
        return font

    # -- geometry ---------------------------------------------------------

    def _layout(self, option):
        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        subtitle_height = QFontMetrics(self.subtitle_font(option.font)).height()

        content_left = option.rect.left() + units.LARGE_SPACING
        content_width = max(1, option.rect.width() - 2 * units.LARGE_SPACING)
        top = option.rect.top() + units.LARGE_SPACING

        cover_rect = QRect(content_left, top, content_width, cover.height())
        title_top = cover_rect.bottom() + 1 + units.SMALL_SPACING
        title_rect = QRect(content_left, title_top, content_width, title_height)
        subtitle_rect = QRect(content_left, title_rect.bottom() + 1, content_width, subtitle_height)
        return CellLayout(cover=cover_rect, title=title_rect, subtitle=subtitle_rect)

    def sizeHint(self, option, index):
        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        subtitle_height = QFontMetrics(self.subtitle_font(option.font)).height()
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
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        self._paint_background(painter, option, palette, selected, hovered)

        layout = self._layout(option)
        self._paint_cover(painter, layout.cover, palette, index)

        title_colour = palette.highlightedText().color() if selected else palette.text().color()
        self._paint_line(
            painter,
            layout.title,
            index.data(Qt.ItemDataRole.DisplayRole) or "",
            self.title_font(option.font, selected=selected),
            title_colour,
        )

        if selected:
            subtitle_colour = QColor(palette.highlightedText().color())
            subtitle_colour.setAlpha(SELECTED_SUBTITLE_ALPHA)
        else:
            subtitle_colour = palette.placeholderText().color()
        self._paint_line(
            painter,
            layout.subtitle,
            index.data(SubtitleRole) or "",
            self.subtitle_font(option.font),
            subtitle_colour,
        )

        painter.restore()

    def _paint_background(self, painter, option, palette, selected, hovered):
        if not (selected or hovered):
            return
        colour = QColor(palette.highlight().color())
        if not selected:
            colour.setAlpha(HOVER_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(option.rect, units.CORNER_RADIUS, units.CORNER_RADIUS)

    def _paint_cover(self, painter, well, palette, index):
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
            return

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
        if ghost:
            self._paint_ghost(painter, art, pixmap, index, state, palette)
        else:
            painter.drawPixmap(art.topLeft(), pixmap)

        border = QColor(palette.text().color())
        border.setAlpha(units.COVER_BORDER_ALPHA)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border)
        painter.drawRoundedRect(art, units.COVER_RADIUS, units.COVER_RADIUS)

    @staticmethod
    def _paint_ghost(painter, rect, pixmap, index, state, palette):
        """A deck not installed yet: an emblem as well as dimming, so colour isn't the only sign"""
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
        )

    @staticmethod
    def _paint_line(painter, rect, text, font, colour):
        painter.setFont(font)
        painter.setPen(colour)
        elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), elided
        )
