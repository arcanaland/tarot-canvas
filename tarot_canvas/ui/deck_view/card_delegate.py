"""Paints a deck's cards as the Library paints decks, and its headings across the view"""

from PyQt6 import sip
from PyQt6.QtCore import QObject, QPersistentModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette, QPixmap
from PyQt6.QtWidgets import QStyle

from tarot_canvas.models.deck import pick_raster
from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.detail import art_loader, art_size, fit_device_size
from tarot_canvas.ui.deck_view.card_model import (
    KIND_CARD,
    KIND_HEADING,
    KIND_NOTE,
    ImageRole,
    ImagesRole,
    KindRole,
)
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_delegate import CellLayout, DeckDelegate
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well

TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
NOTE_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap

# Above every heading but the first, so a section reads as starting, not as one more row
SECTION_SPACE = 2 * units.GRID_UNIT
HEADING_RULE_ALPHA = 51  # ~20% WindowText, the weight of a separator line


class _PendingArt(QObject):
    """The loader's receiver for one decode; it keeps only a weakref, so the cache holds this"""

    def __init__(self, cache, key, dpr):
        super().__init__()
        self._cache = cache
        self.key = key
        self.dpr = dpr
        self.waiting = []  # (view, QPersistentModelIndex)

    def wait(self, view, index):
        persistent = QPersistentModelIndex(index)
        if not any(v is view and p == persistent for v, p in self.waiting):
            self.waiting.append((view, persistent))

    def receive_detail(self, _level, image):
        self._cache.deliver(self, image)


class _ArtCache:
    """Card art decoded off the GUI thread, by (path, well width, well height, dpr)"""

    def __init__(self):
        self._pixmaps = {}  # None for art that can't be read, so it is never asked for again
        self._pending = {}

    def clear(self):
        # A decode still in flight lands on a receiver nothing holds, so the loader drops it
        self._pixmaps.clear()
        self._pending.clear()

    def get(self, path, well, dpr, view, index):
        """The pixmap, or None while it loads or if it can't"""
        key = (path, well.width(), well.height(), round(dpr, 3))
        if key in self._pixmaps:
            return self._pixmaps[key]
        pending = self._pending.get(key)
        if pending is None:
            source = art_size(path)
            size = fit_device_size(source, well, dpr) if source.isValid() else QSize()
            if size.isEmpty():
                self._pixmaps[key] = None
                return None
            pending = self._pending[key] = _PendingArt(self, key, dpr)
            art_loader().request(pending, path, size, 1)
        pending.wait(view, index)
        return None

    def deliver(self, pending, image):
        if self._pending.get(pending.key) is not pending:
            return
        del self._pending[pending.key]
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(pending.dpr)
        self._pixmaps[pending.key] = pixmap
        for view, persistent in pending.waiting:
            if sip.isdeleted(view) or not persistent.isValid():
                continue
            view.update(view.model().index(persistent.row(), persistent.column()))


class CardDelegate(DeckDelegate):
    """A card cell is a deck cell without the subtitle; headings and notes span the view.

    Its parent is the one view it paints, which is the view its art cache repaints.
    """

    def __init__(self, parent=None, density=units.DENSITY_MEDIUM):
        super().__init__(parent, density=density)
        self._art = _ArtCache()
        # Tall enough for whatever the view sets on a heading's line
        self._heading_line_min = 0

    def set_density(self, density):
        changed = super().set_density(density)
        if changed:
            self._art.clear()
        return changed

    # -- fonts ------------------------------------------------------------

    @staticmethod
    def heading_font():
        return typography.font(typography.Role.HEADING_2)

    @staticmethod
    def note_font(base):
        font = QFont(base)
        font.setItalic(True)
        return font

    # -- geometry ---------------------------------------------------------

    def _layout(self, option):
        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        content_left = option.rect.left() + units.LARGE_SPACING
        content_width = max(1, option.rect.width() - 2 * units.LARGE_SPACING)
        top = option.rect.top() + units.LARGE_SPACING

        cover_rect = QRect(content_left, top, content_width, cover.height())
        title_rect = QRect(
            content_left, cover_rect.bottom() + 1 + units.SMALL_SPACING, content_width, title_height
        )
        return CellLayout(cover=cover_rect, title=title_rect, subtitle=QRect())

    def line_width(self, option):
        """The width a heading or note takes: the view's, so nothing shares its line"""
        view = self.parent()
        if view is None:
            return 1
        return max(1, view.viewport().width() - 2 * view.spacing())

    def set_heading_line_min(self, height):
        self._heading_line_min = height

    def heading_layout(self, rect, row):
        """(text line, rule) inside a heading's rect"""
        space = SECTION_SPACE if row > 0 else 0
        line_height = max(QFontMetrics(self.heading_font()).height(), self._heading_line_min)
        text = QRect(rect.left(), rect.top() + space, rect.width(), line_height)
        rule = QRect(rect.left(), text.bottom() + 1 + units.SMALL_SPACING, rect.width(), 1)
        return text, rule

    def sizeHint(self, option, index):
        kind = index.data(KindRole)
        if kind == KIND_HEADING:
            _, rule = self.heading_layout(QRect(0, 0, self.line_width(option), 0), index.row())
            return QSize(rule.width(), rule.bottom() + 1)
        if kind == KIND_NOTE:
            width = self.line_width(option)
            bounds = QFontMetrics(self.note_font(option.font)).boundingRect(
                QRect(0, 0, width, 0), int(NOTE_FLAGS), index.data() or ""
            )
            return QSize(width, bounds.height())

        cover = self.cover_size()
        title_height = QFontMetrics(self.title_font(option.font)).height()
        return QSize(
            cover.width() + 2 * units.LARGE_SPACING,
            cover.height() + title_height + units.SMALL_SPACING + 2 * units.LARGE_SPACING,
        )

    @staticmethod
    def line_palette(option):
        """The view's colours for a heading or note, which Qt would paint as disabled
        because they have no flags"""
        palette = QPalette(option.palette)
        active = bool(option.state & QStyle.StateFlag.State_Active)
        palette.setCurrentColorGroup(
            QPalette.ColorGroup.Active if active else QPalette.ColorGroup.Inactive
        )
        return palette

    def lines_resized(self, model):
        """Re-ask every heading and note for its size, after the view's width changed"""
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(KindRole) != KIND_CARD:
                self.sizeHintChanged.emit(index)

    # -- painting ---------------------------------------------------------

    def paint(self, painter, option, index):
        kind = index.data(KindRole)
        if kind == KIND_CARD:
            super().paint(painter, option, index)
            return

        painter.save()
        palette = self.line_palette(option)
        text = index.data() or ""
        if kind == KIND_NOTE:
            painter.setFont(self.note_font(option.font))
            painter.setPen(palette.placeholderText().color())
            painter.drawText(option.rect, int(NOTE_FLAGS), text)
        else:
            text_rect, rule = self.heading_layout(option.rect, index.row())
            font = self.heading_font()
            painter.setFont(font)
            painter.setPen(palette.windowText().color())
            elided = QFontMetrics(font).elidedText(
                text, Qt.TextElideMode.ElideRight, text_rect.width()
            )
            painter.drawText(text_rect, int(TEXT_FLAGS), elided)

            colour = QColor(palette.windowText().color())
            colour.setAlpha(HEADING_RULE_ALPHA)
            painter.fillRect(rule, colour)
        painter.restore()

    def _paint_subtitle(self, painter, rect, palette, index, selected):
        """A card has only its name"""

    def _paint_cover(self, painter, well, palette, index, selected=False):
        dpr = painter.device().devicePixelRatioF()
        images = index.data(ImagesRole) or {}
        path = pick_raster(images, well.height() * dpr) or index.data(ImageRole)
        pixmap = self._art.get(path, well.size(), dpr, self.parent(), index) if path else None
        if pixmap is None:
            paint_placeholder_well(painter, well, palette)
            return

        art = self._art_rect(well, pixmap)
        painter.drawPixmap(art.topLeft(), pixmap)
        self._paint_cover_border(painter, art, palette)
