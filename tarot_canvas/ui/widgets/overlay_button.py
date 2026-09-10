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

        icon_size = self.style().pixelMetric(QStyle.PixelMetric.PM_ToolBarIconSize, None, self)
        self.setIconSize(QSize(icon_size, icon_size))

        # some math because it's a square in a circle
        self.size_px = math.ceil(icon_size * math.sqrt(2)) + 2 * self.PADDING
        self.setFixedSize(self.size_px, self.size_px)
        self.set_icon(icon_name, fallback)

        self.clicked.connect(on_click)

        parent.installEventFilter(self)
        self.hide()
        self.reposition()

    def set_icon(self, icon_name, fallback):
        icon = QIcon.fromTheme(f"{icon_name}-symbolic")

        if icon.isNull():
            icon = QIcon.fromTheme(icon_name)

        self.setIcon(icon)
        self.setText("" if not icon.isNull() else fallback)

    def reposition(self):
        """'Go to the corner!' - Echo of Doragosa"""
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
