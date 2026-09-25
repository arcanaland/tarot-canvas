"""A message shown in line with the content it is about, as KMessageWidget is."""

from PyQt6.QtCore import QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton

from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import message_border, message_fill


class InlineMessage(QFrame):
    """A line of text, its actions and a close button. Hidden until shown."""

    dismissed = pyqtSignal()

    def __init__(self, close_text="", parent=None):
        super().__init__(parent)
        # Appearing must not pull focus from whatever the person was doing
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.close_button = QToolButton(self)
        self.close_button.setIcon(QIcon.fromTheme("dialog-close"))
        self.close_button.setAutoRaise(True)
        self.close_button.setToolTip(close_text)
        self.close_button.setAccessibleName(close_text)
        self.close_button.clicked.connect(self.dismiss)

        self._layout = QHBoxLayout(self)
        margin = units.LARGE_SPACING
        self._layout.setContentsMargins(
            margin, units.SMALL_SPACING, units.SMALL_SPACING, units.SMALL_SPACING
        )
        self._layout.setSpacing(units.SMALL_SPACING)
        self._layout.addWidget(self.label, 1)
        self._layout.addWidget(self.close_button)

        self.action_buttons = []
        self.hide()

    def show_message(self, text, actions=()):
        self.label.setText(text)
        self._set_actions(actions)
        self.show()

    def dismiss(self):
        """Closed by the person, as distinct from hidden by its owner."""
        self.hide()
        self.dismissed.emit()

    def _set_actions(self, actions):
        for button in self.action_buttons:
            self._layout.removeWidget(button)
            button.deleteLater()
        self.action_buttons = []

        for action in actions:
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setAutoRaise(True)
            self._layout.insertWidget(self._layout.indexOf(self.close_button), button)
            self.action_buttons.append(button)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(message_border(self.palette()))
        painter.setBrush(message_fill(self.palette()))
        # Half a pixel in, so the one-pixel border lands on whole pixels
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(rect, units.CORNER_RADIUS, units.CORNER_RADIUS)
        painter.end()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self.update()
