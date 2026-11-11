from dataclasses import dataclass, replace

from PyQt6.QtCore import QEvent, QModelIndex, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PyQt6.QtWidgets import QLineEdit, QStyle, QStyledItemDelegate, QToolTip

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.commands import tooltip_with_keys
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.covers.ghost import paint_placeholder_well
from tarot_canvas.ui.library.roles import (
    SELECTED_SUBTITLE_ALPHA,
    BadgeRole,
    CoverPathRole,
    PreviewRole,
    SubtitleRole,
)

THUMBNAIL_ASPECT = 0.57

MENU_ICON_SIZE = 16
MENU_BUTTON_SIZE = MENU_ICON_SIZE + 2 * units.SMALL_SPACING


@dataclass(frozen=True)
class RowButton:
    """A button painted at a row's trailing end"""

    icon: str  # a theme name
    tooltip: str
    signal: str  # the delegate's signal it emits: (the row, where a menu should open)
    command: str | None = None  # whose key the tooltip names


@dataclass(frozen=True)
class NoteRowLayout:
    well: QRect
    title: QRect
    subtitle: QRect
    preview: QRect
    buttons: tuple  # a QRect per row button, in their order
    menu: QRect  # null without a menu button


class NoteRowDelegate(QStyledItemDelegate):
    WELL_ASPECT = THUMBNAIL_ASPECT

    # the row, and where on screen its menu should open
    menuRequested = pyqtSignal(QModelIndex, QPoint)

    def __init__(
        self,
        parent=None,
        cover_cache=None,
        *,
        thumbnail=True,
        menu_button=False,
        menu_tooltip="",
        reading=False,
        buttons=(),
        preview=True,
    ):
        super().__init__(parent)
        self._reading = reading
        self._preview = preview
        self._cover_cache = cover_cache or CoverCache()
        self._thumbnail = thumbnail
        # The menu button, when there is one, comes last
        self._menu_button = menu_button
        menu = (RowButton("overflow-menu", menu_tooltip, "menuRequested"),) if menu_button else ()
        self._buttons = tuple(buttons) + menu

    def _fonts(self, option, selected):
        title = QFont(option.font)
        title.setBold(selected)
        return title, typography.font(typography.Role.SMALL, reading=self._reading)

    def _line_heights(self, option):
        title, small = self._fonts(option, False)
        return QFontMetrics(title).height(), QFontMetrics(small).height()

    def _text_height(self, option):
        title_height, small_height = self._line_heights(option)
        return title_height + (2 if self._preview else 1) * small_height

    def _layout(self, option):
        title_height, small_height = self._line_heights(option)
        text_height = self._text_height(option)

        top = option.rect.top() + units.LARGE_SPACING
        well_width = max(1, round(text_height * self.WELL_ASPECT)) if self._thumbnail else 0
        well = QRect(option.rect.left() + units.LARGE_SPACING, top, well_width, text_height)

        left = well.left() + (well_width + units.LARGE_SPACING if self._thumbnail else 0)
        right = option.rect.right() + 1 - units.LARGE_SPACING

        # Laid out from the trailing end, side by side
        buttons = []
        for _button in self._buttons:
            rect = QRect(right - MENU_BUTTON_SIZE, 0, MENU_BUTTON_SIZE, MENU_BUTTON_SIZE)
            rect.moveCenter(QPoint(rect.center().x(), option.rect.center().y()))
            buttons.insert(0, rect)
            right = rect.left()
        if buttons:
            right -= units.SMALL_SPACING
        menu = buttons[-1] if self._menu_button else QRect()

        width = max(1, right - left)
        title = QRect(left, top, width, title_height)
        subtitle = QRect(left, title.bottom() + 1, width, small_height)
        preview = (
            QRect(left, subtitle.bottom() + 1, width, small_height) if self._preview else QRect()
        )
        return NoteRowLayout(
            well=well,
            title=title,
            subtitle=subtitle,
            preview=preview,
            buttons=tuple(buttons),
            menu=menu,
        )

    def sizeHint(self, option, index):
        return QSize(units.GRID_UNIT, self._text_height(option) + 2 * units.LARGE_SPACING)

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
            self._paint_well(painter, layout.well, palette, index)

        title_font, small_font = self._fonts(option, selected)
        badge = index.data(BadgeRole)
        if badge:
            layout = self._paint_badge(painter, layout, badge, small_font, palette, selected)
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
        if self._preview:
            _draw(painter, layout.preview, index.data(PreviewRole), small_font, dim_colour)

        mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
        for button, rect in zip(self._buttons, layout.buttons, strict=False):
            icon_rect = QRect(0, 0, MENU_ICON_SIZE, MENU_ICON_SIZE)
            icon_rect.moveCenter(rect.center())
            QIcon.fromTheme(button.icon).paint(
                painter, icon_rect, Qt.AlignmentFlag.AlignCenter, mode
            )

        painter.restore()

    def _paint_badge(self, painter, layout, badge, font, palette, selected):
        """badge at the text's trailing end, centred on the row; the layout its text keeps"""
        width = QFontMetrics(font).horizontalAdvance(badge)
        right = layout.title.right() + 1
        rect = QRect(
            right - width, layout.title.top(), width, layout.well.height() or layout.title.height()
        )
        painter.setFont(font)
        painter.setPen(palette.highlightedText().color() if selected else palette.text().color())
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), badge
        )

        def narrowed(text_rect):
            if text_rect.isNull():
                return text_rect
            return text_rect.adjusted(0, 0, -(width + units.LARGE_SPACING), 0)

        return replace(
            layout,
            title=narrowed(layout.title),
            subtitle=narrowed(layout.subtitle),
            preview=narrowed(layout.preview),
        )

    # -- the row's buttons --------------------------------------------------

    def _button_at(self, pos, option):
        """The row button under pos and its rect, or (None, None)"""
        for button, rect in zip(self._buttons, self._layout(option).buttons, strict=False):
            if rect.contains(pos):
                return button, rect
        return None, None

    def editorEvent(self, event, model, option, index):
        kind = event.type()
        if (
            kind in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            button, rect = self._button_at(event.position().toPoint(), option)
            if button is not None:
                if kind == QEvent.Type.MouseButtonRelease:
                    getattr(self, button.signal).emit(index, self._anchor(event, option, rect))
                # Consumed, so the click on a button doesn't also open the row
                return True
        return super().editorEvent(event, model, option, index)

    def _anchor(self, event, option, rect):
        """Under the button, where a tool button's menu would drop."""
        view = option.widget
        if view is not None and hasattr(view, "viewport"):
            return view.viewport().mapToGlobal(rect.bottomLeft())
        return event.globalPosition().toPoint()

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            button, _rect = self._button_at(event.pos(), option)
            if button is not None and button.tooltip:
                text = button.tooltip
                if button.command is not None:
                    text = tooltip_with_keys(text, button.command)
                QToolTip.showText(event.globalPos(), text, view)
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

    def _paint_well(self, painter, well, palette, index):
        self._paint_thumbnail(painter, well, palette, index.data(CoverPathRole))

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


class IconRowDelegate(NoteRowDelegate):
    """A row whose well is a square holding its icon"""

    WELL_ASPECT = 1.0

    def _paint_well(self, painter, well, palette, index):
        index.data(Qt.ItemDataRole.DecorationRole).paint(painter, well)
