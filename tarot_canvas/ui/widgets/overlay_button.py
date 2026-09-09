import math

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QStyle, QToolButton

from tarot_canvas.ui.widgets.overlay_chrome import paint_surface, text_color


class OverlayButton(QToolButton):
    """A round icon button floating over a content view in a corner."""

    MARGIN = 12
    GAP = 8
    PADDING = 6

    def __init__(self, parent, icon_name, fallback, tooltip, on_click, row=0):
        super().__init__(parent)
        self.row = row
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(tooltip)
        # Sized off the style's icon metric, not a constant, so the button grows
        # with the rest of the UI when the system font size does
        # (hig/accessibility.md asks us to check that case).
        icon_size = self.style().pixelMetric(QStyle.PixelMetric.PM_ToolBarIconSize, None, self)
        self.setIconSize(QSize(icon_size, icon_size))
        # The icon is a square inside a circle, so the padding has to clear the
        # inscribed square (side d/sqrt(2)), not the bounding box. Sizing as if
        # it were a square button leaves the glyph almost touching the rim.
        self.size_px = math.ceil(icon_size * math.sqrt(2)) + 2 * self.PADDING
        self.setFixedSize(self.size_px, self.size_px)
        self.set_icon(icon_name, fallback)

        self.clicked.connect(on_click)

        # The button is a sibling of the view's viewport rather than a laid-out
        # widget, so nothing repositions it for us.
        parent.installEventFilter(self)
        self.hide()
        self.reposition()

    def set_icon(self, icon_name, fallback):
        """Icons say what the next press does, not what state we are in."""
        # hig/icons: at 22px, ask for symbolic. It is only a preference -- the
        # theme decides -- but without the suffix Breeze may hand back the
        # full-colour variant, whose filled slabs fight the artwork underneath.
        icon = QIcon.fromTheme(f"{icon_name}-symbolic")
        if icon.isNull():
            icon = QIcon.fromTheme(icon_name)
        self.setIcon(icon)
        # Breeze may be absent (bare test environments, non-KDE sessions); an
        # empty round button would be an invisible control.
        self.setText("" if not icon.isNull() else fallback)

    def reposition(self):
        """Sit in the top-trailing corner of the view we float over.

        Top rather than bottom: the bottom of a tarot card is its title
        cartouche, the one part of the artwork carrying text.
        """
        parent = self.parentWidget()
        if parent is None:
            return
        if parent.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            x = self.MARGIN
        else:
            x = parent.width() - self.width() - self.MARGIN
        self.move(x, self.MARGIN + self.row * (self.size_px + self.GAP))

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self.reposition()
            self.raise_()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        """Draw the disc ourselves rather than asking a stylesheet for one.

        Setting any stylesheet on a QToolButton hands the whole widget to
        QStyleSheetStyle, which drops every state the sheet does not itself
        redeclare -- the pressed state included, which is why the sheet version
        gave no feedback on click. Painting it is also the only way to get an
        antialiased disc: Qt draws a QSS `border-radius` as four edges plus four
        corner arcs, and a translucent rim composites twice at each seam.
        """
        painter = QPainter(self)
        active = self.underMouse() or self.isDown()
        paint_surface(self, painter, active=active)

        if self.icon().isNull():
            painter.setPen(text_color(self))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        else:
            mode = QIcon.Mode.Active if active else QIcon.Mode.Normal
            self.icon().paint(painter, self.icon_rect(), Qt.AlignmentFlag.AlignCenter, mode)

    def icon_rect(self):
        """Where the glyph goes -- iconSize, centred, NOT the whole button.

        QIcon.paint scales to whatever rect it is given, so passing self.rect()
        silently overrides setIconSize and draws a glyph the full width of the
        disc, hard against the rim.
        """
        rect = QRect(QPoint(0, 0), self.iconSize())
        rect.moveCenter(self.rect().center())
        return rect

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def setVisible(self, visible):
        super().setVisible(visible)
        if visible:
            self.reposition()
            self.raise_()
