from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QModelIndex, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter
from PyQt6.QtWidgets import QLineEdit, QStyle, QStyledItemDelegate, QToolTip

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_delegate import SELECTED_SUBTITLE_ALPHA, SUBTITLE_SCALE
from tarot_canvas.ui.library.deck_model import CoverPathRole, SubtitleRole
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well
from tarot_canvas.ui.library.notes_model import PreviewRole

THUMBNAIL_ASPECT = 0.57

MENU_ICON_SIZE = 16
MENU_BUTTON_SIZE = MENU_ICON_SIZE + 2 * units.SMALL_SPACING


@dataclass(frozen=True)
class NoteRowLayout:
    well: QRect
    title: QRect
    subtitle: QRect
    preview: QRect
    menu: QRect  # null without a menu button


class NoteRowDelegate(QStyledItemDelegate):
    # the row, and where on screen its menu should open
    menuRequested = pyqtSignal(QModelIndex, QPoint)

    def __init__(
        self, parent=None, cover_cache=None, *, thumbnail=True, menu_button=False, menu_tooltip=""
    ):
        super().__init__(parent)
        self._cover_cache = cover_cache or CoverCache()
        self._thumbnail = thumbnail
        self._menu_button = menu_button
        self._menu_tooltip = menu_tooltip

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
        well_width = max(1, round(text_height * THUMBNAIL_ASPECT)) if self._thumbnail else 0
        well = QRect(option.rect.left() + units.LARGE_SPACING, top, well_width, text_height)

        left = well.left() + (well_width + units.LARGE_SPACING if self._thumbnail else 0)
        right = option.rect.right() + 1 - units.LARGE_SPACING

        menu = QRect()
        if self._menu_button:
            menu = QRect(right - MENU_BUTTON_SIZE, 0, MENU_BUTTON_SIZE, MENU_BUTTON_SIZE)
            menu.moveCenter(QPoint(menu.center().x(), option.rect.center().y()))
            right = menu.left() - units.SMALL_SPACING

        width = max(1, right - left)
        title = QRect(left, top, width, title_height)
        subtitle = QRect(left, title.bottom() + 1, width, small_height)
        preview = QRect(left, subtitle.bottom() + 1, width, small_height)
        return NoteRowLayout(well=well, title=title, subtitle=subtitle, preview=preview, menu=menu)

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
        if self._thumbnail:
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

        if self._menu_button:
            icon_rect = QRect(0, 0, MENU_ICON_SIZE, MENU_ICON_SIZE)
            icon_rect.moveCenter(layout.menu.center())
            mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
            QIcon.fromTheme("overflow-menu").paint(
                painter, icon_rect, Qt.AlignmentFlag.AlignCenter, mode
            )

        painter.restore()

    # -- the menu button ----------------------------------------------------

    def _on_menu_button(self, event, option):
        return self._menu_button and self._layout(option).menu.contains(event.position().toPoint())

    def editorEvent(self, event, model, option, index):
        kind = event.type()
        if (
            kind in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
            and event.button() == Qt.MouseButton.LeftButton
            and self._on_menu_button(event, option)
        ):
            if kind == QEvent.Type.MouseButtonRelease:
                self.menuRequested.emit(index, self._menu_anchor(event, option))
            # Consumed, so the click that opens the menu doesn't also open the note
            return True
        return super().editorEvent(event, model, option, index)

    def _menu_anchor(self, event, option):
        """Under the button, where a tool button's menu would drop."""
        view = option.widget
        if view is not None and hasattr(view, "viewport"):
            return view.viewport().mapToGlobal(self._layout(option).menu.bottomLeft())
        return event.globalPosition().toPoint()

    def helpEvent(self, event, view, option, index):
        if (
            event.type() == QEvent.Type.ToolTip
            and self._menu_button
            and self._menu_tooltip
            and self._layout(option).menu.contains(event.pos())
        ):
            QToolTip.showText(event.globalPos(), self._menu_tooltip, view)
            return True
        return super().helpEvent(event, view, option, index)

    # -- renaming in place --------------------------------------------------

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setFont(self._fonts(option, False)[0])
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.EditRole) or "")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        title = self._layout(option).title
        height = max(title.height(), editor.sizeHint().height())
        editor.setGeometry(title.left(), title.center().y() - height // 2, title.width(), height)

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
