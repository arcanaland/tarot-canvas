"""A panel placed in the canvas (background chooser, arc arranger)"""

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QLabel,
    QLayout,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography

# Kirigami's cornerRadius
CORNER_RADIUS = 5
# How far the outline is mixed from the window's colour toward its text's
OUTLINE_MIX = 0.2

# Where the panel may sit, in the order a tie is broken
CORNERS = ("top_right", "top_left", "bottom_right", "bottom_left")


def window_margin(style):
    """The style's margin for a window's contents, which a panel over the canvas also gets"""
    option = QStyleOption()
    option.state |= QStyle.StateFlag.State_Window
    return style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin, option)


def outline_colour(palette):
    """A line that stands out from the panel's fill, in a dark scheme as in a light one"""
    fill = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return QColor.fromRgbF(
        *(
            f + (t - f) * OUTLINE_MIX
            for f, t in zip(fill.getRgbF()[:3], text.getRgbF()[:3], strict=True)
        )
    )


def plain_label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class CanvasPanel(QFrame):
    applied = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, title, view, parent):
        super().__init__(parent)
        # Painted opaque by paintEvent, with an outline, whatever the canvas under it is
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.view = view
        self.corner = CORNERS[0]
        self.opened = False
        self.finished = False

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        self.buttons.rejected.connect(self.cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)

        # The menu entry's label, echoed as a dialog's title would be
        self.title = plain_label(title)
        typography.apply(self.title, typography.Role.HEADING_4)
        self.hide()

    def lay_out(self, *parts):
        """The heading, then parts (layouts or widgets), then Cancel and Apply"""
        layout = QVBoxLayout(self)
        margin = window_margin(self.style())
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(self.title)
        for part in parts:
            if isinstance(part, QLayout):
                layout.addLayout(part)
            else:
                layout.addWidget(part)
        # A gap between groups, twice the one between rows
        layout.addSpacing(layout.spacing())
        layout.addWidget(self.buttons)

    # -- what a subclass gives ---------------------------------------------

    def covered_rect(self):
        """The scene rect the panel should hide least of"""
        raise NotImplementedError

    def restore(self):
        """Put back what was there when the panel opened"""
        raise NotImplementedError

    # -- where it sits -----------------------------------------------------

    def _viewport_rect(self):
        """The view's viewport, in the coordinates of the panel's parent"""
        viewport = self.view.viewport()
        return QRect(viewport.mapTo(self.parentWidget(), QPoint(0, 0)), viewport.size())

    def _corner_rect(self, corner):
        """Where the panel goes at `corner`, in its parent's coordinates"""
        inset = window_margin(self.style())
        area = self._viewport_rect().adjusted(inset, inset, -inset, -inset)
        rect = QRect(QPoint(0, 0), self.size())
        if corner.startswith("top"):
            rect.moveTop(area.top())
        else:
            rect.moveBottom(area.bottom())
        if corner.endswith("left"):
            rect.moveLeft(area.left())
        else:
            rect.moveRight(area.right())
        return rect

    def _choose_corner(self):
        """The corner that hides least of covered_rect; top right on a tie"""
        covered = self.covered_rect()
        if covered.isEmpty():
            return CORNERS[0]
        cards = self.view.mapFromScene(covered).boundingRect()
        cards.translate(self._viewport_rect().topLeft())

        def hidden(corner):
            overlap = self._corner_rect(corner).intersected(cards)
            return 0 if overlap.isEmpty() else overlap.width() * overlap.height()

        return min(CORNERS, key=hidden)

    def place(self):
        self.setGeometry(self._corner_rect(self.corner))

    def refit(self):
        """Take the size the rows now need, in the same corner"""
        if self.finished:
            return
        # Inside out: a nested widget's layout learns of its hidden rows only when it activates
        nested = [widget.layout() for widget in reversed(self.findChildren(QWidget))]
        for layout in [*nested, self.layout()]:
            if layout is not None:
                layout.invalidate()
                layout.activate()
        self.adjustSize()
        self.place()

    # -- opening and closing -----------------------------------------------

    def open(self):
        """Show the panel in the corner that hides least of what it covers"""
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()
        self.corner = self._choose_corner()
        self.place()
        self.view.installEventFilter(self)
        self.opened = True
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == QEvent.Type.Resize:
            self.place()
        return False

    def apply(self):
        self._finish(applied=True)

    def cancel(self):
        self._finish(applied=False)

    def _finish(self, applied):
        if self.finished:
            return
        self.finished = True
        if not applied:
            self.restore()
        self.view.removeEventFilter(self)
        self.hide()
        self.closed.emit()
        if applied:
            self.applied.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        # Hidden other than by Apply or Cancel (its tab closed, say): nothing was applied
        if self.opened and not event.spontaneous():
            self.cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(outline_colour(self.palette()))
        painter.setBrush(self.palette().color(QPalette.ColorRole.Window))
        # Half a pixel in, so the 1px outline falls on whole pixels
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS
        )
