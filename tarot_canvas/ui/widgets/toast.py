from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtGui import QPainter, QPalette
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel

from tarot_canvas.ui.widgets.overlay_chrome import paint_surface, text_color


class Toast(QLabel):
    """A transient toast message"""

    MARGIN = 24
    HOLD_MS = 2200
    FADE_MS = 400
    OPACITY = 0.85
    RADIUS = 6

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(16, 8, 16, 8)
        self.setForegroundRole(QPalette.ColorRole.WindowText)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.WindowText, text_color(self))
        self.setPalette(palette)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(self.OPACITY)
        self.setGraphicsEffect(self._opacity)

        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.finished.connect(self.hide)

        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._start_fade)

        # A view reports its resize before it has resized its own viewport.
        self._replace = QTimer(self)
        self._replace.setSingleShot(True)
        self._replace.setInterval(0)
        self._replace.timeout.connect(self.reposition)

        parent.installEventFilter(self)
        self.hide()

    def show_message(self, text, hold_ms=None):
        """Show text, hold it, then fade it out"""
        self._fade.stop()
        self.setText(text)
        self.adjustSize()
        self._opacity.setOpacity(self.OPACITY)
        self.reposition()
        self.show()
        self.raise_()

        # The mode that shows a hint usually resizes the view on its way in
        self._replace.start()
        self._hold.start(self.HOLD_MS if hold_ms is None else hold_ms)

    def dismiss(self):
        self._hold.stop()
        self._fade.stop()
        self._replace.stop()
        self.hide()

    def reposition(self):
        """Beside the content"""
        parent = self.parentWidget()
        if parent is None:
            return
        position = None
        if hasattr(parent, "clear_band_position"):
            position = parent.clear_band_position(self.size())
        if position is None:
            x = max(0, (parent.width() - self.width()) // 2)
            position = QPoint(x, parent.height() - self.height() - self.MARGIN)
        self.move(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_surface(self, painter, radius=self.RADIUS)
        painter.end()
        # QLabel draws the text inside our contents rect, on top of the surface.
        super().paintEvent(event)

    def _start_fade(self):
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._replace.start()
        return super().eventFilter(watched, event)
