"""Paints one deck cell: cover, title, subtitle — all in palette colours."""

from dataclasses import dataclass

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_model import CoverPathRole, SubtitleRole

# Alpha applied to palette colours. Everything the delegate draws is derived
# from QPalette, so the view follows the user's colour scheme in both light and
# dark without a single hex literal in this file.
HOVER_ALPHA = 38  # ~15% Highlight behind a hovered cell
COVER_BORDER_ALPHA = 26  # ~10% Text as the cover hairline
PLACEHOLDER_WELL_ALPHA = 20
SELECTED_SUBTITLE_ALPHA = 200

SUBTITLE_SCALE = 0.85
PLACEHOLDER_ICON_FRACTION = 0.4


@dataclass(frozen=True)
class CellLayout:
    """Sub-rects of one cell. Pure geometry, so it is testable without a painter."""

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
        """Returns True when the density actually changed, so the view can relayout."""
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
        # The HIG asks for bold on the selected grid item, and only there.
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
        """Sub-rects for a cell occupying `option.rect`.

        One helper owns all the arithmetic so the paint path stays a
        transcription of it, and so the geometry can be unit-tested.
        """
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

        if pixmap is None:
            self._paint_placeholder(painter, well, palette)
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
        painter.drawPixmap(art.topLeft(), pixmap)

        border = QColor(palette.text().color())
        border.setAlpha(COVER_BORDER_ALPHA)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border)
        painter.drawRoundedRect(art, units.COVER_RADIUS, units.COVER_RADIUS)

    def _paint_placeholder(self, painter, well, palette):
        """A well the same footprint as real art, so rows never lose alignment."""
        ground = QColor(palette.text().color())
        ground.setAlpha(PLACEHOLDER_WELL_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ground)
        painter.drawRoundedRect(well, units.COVER_RADIUS, units.COVER_RADIUS)

        icon = QIcon.fromTheme("image-missing")
        if icon.isNull():
            return
        extent = max(16, round(min(well.width(), well.height()) * PLACEHOLDER_ICON_FRACTION))
        target = QRect(0, 0, extent, extent)
        target.moveCenter(well.center())
        icon.paint(painter, target, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Disabled)

    @staticmethod
    def _paint_line(painter, rect, text, font, colour):
        painter.setFont(font)
        painter.setPen(colour)
        elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), elided
        )
