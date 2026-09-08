from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel


class Toast(QLabel):
    """A transient message floating over a content view, then fading away.

    The KDE analogue is a passive notification (hig/status_changes.md): for
    "ignorable or low-importance messages". That page also asks us to minimise
    status messages, and this one obeys the spirit of it -- it does not announce
    that something succeeded (the screen already showed that), it teaches the
    keystroke that undoes a mode which has just hidden every other way out.
    """

    MARGIN = 24
    HOLD_MS = 2200
    FADE_MS = 400
    OPACITY = 0.85

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "QLabel { border: 1px solid rgba(255, 255, 255, 60); border-radius: 6px;"
            " background: rgba(0, 0, 0, 170); color: white; padding: 8px 16px; }"
        )

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
        self._hold.start(self.HOLD_MS if hold_ms is None else hold_ms)

    def dismiss(self):
        """Take it away now, without a fade (the mode it described is over)"""
        self._hold.stop()
        self._fade.stop()
        self.hide()

    def reposition(self):
        """Beside the content if the parent knows of somewhere clear of it.

        A view that can say where its content is not -- ZoomableImageView, whose
        cards leave wide empty bands either side -- gets to place us there, so a
        hint never sits on the thing it is a hint about. Anything else falls back
        to the bottom of the view.
        """
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

    def _start_fade(self):
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.reposition()
        return super().eventFilter(watched, event)
