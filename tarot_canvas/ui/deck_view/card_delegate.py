import weakref

from PyQt6 import sip
from PyQt6.QtCore import QObject, QPersistentModelIndex, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette, QPixmap
from PyQt6.QtWidgets import QStyle

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.canvas.detail import art_loader, art_size, fit_device_size
from tarot_canvas.ui.covers.cache import modified_ns
from tarot_canvas.ui.covers.ghost import PLACEHOLDER_ICON_FRACTION, paint_placeholder_well
from tarot_canvas.ui.deck_view.card_model import (
    KIND_BACK,
    KIND_CARD,
    KIND_HEADING,
    KIND_NOTE,
    BackPathRole,
    CanonicalRole,
    CardRole,
    KindRole,
)
from tarot_canvas.ui.deck_view.tableau_model import KIND_GHOST, KIND_LABEL, DimmedRole
from tarot_canvas.ui.library.decks.delegate import CellLayout, DeckDelegate
from tarot_canvas.ui.strings import DECK_VIEW

TEXT_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
NOTE_FLAGS = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap

SECTION_SPACE = 2 * units.GRID_UNIT
HEADING_RULE_ALPHA = 51
DIMMED_OPACITY = 0.3
EMPTY_SLOT_ICON = "list-add"
# Quiet across a grid of empty slots, full on the one under the pointer
EMPTY_SLOT_ICON_FRACTION = 0.25
EMPTY_SLOT_ICON_OPACITY = 0.5


class _PendingArt(QObject):
    """The loader's receiver for one decode"""

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
    """Card art decoded off the GUI thread"""

    def __init__(self):
        self._pixmaps = {}
        self._pending = {}

    def clear(self):
        self._pixmaps.clear()
        self._pending.clear()

    def get(self, path, well, dpr, view, index):
        """The pixmap, or None while it loads"""
        modified = modified_ns(path)
        if modified is None:
            return None
        key = (path, modified, well.width(), well.height(), round(dpr, 3))

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
    def __init__(self, parent=None, density=units.DENSITY_MEDIUM, editable=False):
        super().__init__(parent, density=density)
        self.editable = editable
        # The cell a drag is over
        self.drop_target = None
        # An empty slot's shape: the deck's placed art, once there is some
        self.slot_shape = None
        self._hovered = False
        self._art = _ArtCache()
        # Two views share this delegate; art arriving repaints the one that asked.
        # Weak, so a deleted view isn't kept wrapped
        self._view = weakref.ref(parent) if parent is not None else lambda: None

    def set_slot_shape(self, deck):
        """Shape empty slots like the deck's first placed card, so filling one doesn't resize it"""
        self.slot_shape = None
        for card in deck.cards:
            path = card.default_image()
            size = art_size(path) if path else QSize()
            if not size.isEmpty():
                self.slot_shape = size
                return

    def _slot_rect(self, well):
        """Where an empty slot goes in the well, placed as _art_rect places art"""
        if self.slot_shape is None:
            return well
        slot = QRect(
            QPoint(0, 0), self.slot_shape.scaled(well.size(), Qt.AspectRatioMode.KeepAspectRatio)
        )
        slot.moveCenter(well.center())
        slot.moveBottom(well.bottom())
        return slot

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

    def sizeHint(self, option, index):
        kind = index.data(KindRole)
        if kind is None:
            return QSize()
        if kind == KIND_LABEL:
            metrics = QFontMetrics(index.data(Qt.ItemDataRole.FontRole) or option.font)
            return QSize(
                metrics.horizontalAdvance(index.data() or "") + 2 * units.LARGE_SPACING,
                metrics.height() + 2 * units.SMALL_SPACING,
            )
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
        palette = QPalette(option.palette)
        active = bool(option.state & QStyle.StateFlag.State_Active)
        palette.setCurrentColorGroup(
            QPalette.ColorGroup.Active if active else QPalette.ColorGroup.Inactive
        )
        return palette

    # -- painting ---------------------------------------------------------

    def paint(self, painter, option, index):
        if option.widget is not None:
            self._view = weakref.ref(option.widget)
        kind = index.data(KindRole)
        if kind in (KIND_CARD, KIND_BACK):
            if self.drop_target is not None and self.drop_target == index:
                option.state |= QStyle.StateFlag.State_MouseOver
            self._hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
            if index.data(DimmedRole):
                # Find's non-matches in the tableau, which keeps every slot
                painter.save()
                painter.setOpacity(DIMMED_OPACITY)
                super().paint(painter, option, index)
                painter.restore()
            else:
                super().paint(painter, option, index)
            return
        if kind is None:
            return

        painter.save()
        palette = self.line_palette(option)
        text = index.data() or ""
        if kind == KIND_GHOST:
            paint_placeholder_well(painter, self._layout(option).cover, palette)
        elif kind == KIND_LABEL:
            painter.setFont(index.data(Qt.ItemDataRole.FontRole) or option.font)
            painter.setPen(palette.windowText().color())
            rect = option.rect.adjusted(
                units.LARGE_SPACING, units.SMALL_SPACING, -units.LARGE_SPACING, -units.SMALL_SPACING
            )
            elided = painter.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, rect.width()
            )
            painter.drawText(rect, int(index.data(Qt.ItemDataRole.TextAlignmentRole)), elided)
        elif kind == KIND_NOTE:
            painter.setFont(self.note_font(option.font))
            painter.setPen(palette.placeholderText().color())
            painter.drawText(option.rect, int(NOTE_FLAGS), text)
        else:
            text_rect, rule = self.heading_layout(option.rect, index.row())
            font = self.heading_font()
            painter.setFont(font)
            painter.setPen(palette.windowText().color())
            metrics = QFontMetrics(font)
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, int(TEXT_FLAGS), elided)

            canonical = index.data(CanonicalRole)
            if canonical and elided == text:
                # The specification's name, set back in the de-emphasised tone
                aside = f" {DECK_VIEW['canonical_suit'].format(suit=canonical)}"
                aside_rect = text_rect.adjusted(metrics.horizontalAdvance(text), 0, 0, 0)
                painter.setPen(palette.placeholderText().color())
                painter.drawText(
                    aside_rect,
                    int(TEXT_FLAGS),
                    metrics.elidedText(aside, Qt.TextElideMode.ElideRight, aside_rect.width()),
                )

            colour = QColor(palette.windowText().color())
            colour.setAlpha(HEADING_RULE_ALPHA)
            painter.fillRect(rule, colour)
        painter.restore()

    def _paint_subtitle(self, painter, rect, palette, index, selected):
        """A card has only its name"""

    def _paint_cover(self, painter, well, palette, index, selected=False):
        dpr = painter.device().devicePixelRatioF()
        if index.data(KindRole) == KIND_BACK:
            path = index.data(BackPathRole)
        else:
            card = index.data(CardRole)
            path = card and (card.raster_for(well.height() * dpr) or card.default_image())
        pixmap = (
            self._art.get(path, well.size(), dpr, self._view() or self.parent(), index)
            if path
            else None
        )
        if pixmap is None:
            if self.editable and not path:
                lit = selected or self._hovered
                paint_placeholder_well(
                    painter,
                    self._slot_rect(well),
                    palette,
                    EMPTY_SLOT_ICON,
                    icon_fraction=PLACEHOLDER_ICON_FRACTION if lit else EMPTY_SLOT_ICON_FRACTION,
                    icon_opacity=1.0 if lit else EMPTY_SLOT_ICON_OPACITY,
                )
            else:
                paint_placeholder_well(painter, well, palette)
            return

        art = self._art_rect(well, pixmap)
        painter.drawPixmap(art.topLeft(), pixmap)
        self._paint_cover_border(painter, art, palette)
