from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QFrame, QLabel, QStyle, QStyleOption, QToolButton, QVBoxLayout

from tarot_canvas.ui.tabs.card_view.passage_metrics import column_width

ICON = "help-contextual"

# The HIG's wrap width for a paragraph
MAX_TEXT_WIDTH = 450


def _help_icon():
    """The theme's help icon, or a null icon where it has none"""
    return QIcon.fromTheme(ICON) if QIcon.hasThemeIcon(ICON) else QIcon()


def placed(anchor, size, screen):
    """Where a popup of `size` goes: its top left at `anchor`, moved back onto `screen`"""
    x = max(screen.left(), min(anchor.x(), screen.right() + 1 - size.width()))
    y = max(screen.top(), min(anchor.y(), screen.bottom() + 1 - size.height()))
    return QPoint(x, y)


class HelpPopup(QFrame):
    """A paragraph under its button. Esc or a click anywhere else closes it."""

    def __init__(self, text, button):
        super().__init__(button, Qt.WindowType.Popup)
        self.button = button

        layout = QVBoxLayout(self)
        self.label = QLabel(text)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setOpenExternalLinks(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(self.label)
        self._fit_label()

    def _fit_label(self):
        """As wide as the text on one line, up to a paragraph's width, then wrapped"""
        cap = min(MAX_TEXT_WIDTH, column_width(self.label.font()))
        self.label.setWordWrap(False)
        one_line = self.label.sizeHint().width()
        self.label.setWordWrap(True)
        self.label.setFixedWidth(min(cap, one_line))

    def paintEvent(self, event):
        # A menu's surface: a frame styles draw for no other popup (Breeze draws a StyledPanel
        # popup as bare text over whatever is under it)
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelMenu, option, painter, self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_FrameMenu, option, painter, self)

    def mousePressEvent(self, event):
        # A click on the button closes the popup. Where Qt replays that press to the widget
        # under it (Windows), it would reach the button and reopen the popup
        button = self.button
        if button.rect().contains(button.mapFromGlobal(event.globalPosition().toPoint())):
            self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        super().mousePressEvent(event)

    def open_under(self, button):
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, False)
        # The style's frame and the font are known only once polished
        self.ensurePolished()
        self._fit_label()
        self.layout().activate()
        self.adjustSize()
        anchor = button.mapToGlobal(button.rect().bottomLeft())
        self.move(placed(anchor, self.size(), button.screen().availableGeometry()))
        self.show()


class ContextualHelpButton(QToolButton):
    """A help icon that opens a short explanation, with links, under itself.

    Not a tooltip: a link in one can't be relied on to be clickable. Without a theme icon it
    shows its tooltip as its label, and with neither it isn't shown at all.
    """

    def __init__(self, text, tooltip="", accessible_name="", parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setToolTip(tooltip)
        self.setAccessibleName(accessible_name)
        icon = _help_icon()
        if not icon.isNull():
            self.setIcon(icon)
        else:
            self.setText(tooltip)
        if icon.isNull() and not tooltip:
            self.setVisible(False)

        self.popup = HelpPopup(text, self)
        self.clicked.connect(self._toggle)

    def _toggle(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            self.popup.open_under(self)
