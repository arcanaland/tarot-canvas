from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QToolButton


class ExitFullscreenButton(QToolButton):
    """The way out of fullscreen, floating over a content view.

    There is deliberately no matching *enter* button. Entering is never hidden
    -- it is in the View menu, on Ctrl+Shift+F and on F -- so the HIG's rule
    against controls that appear on hover does not bite: it constrains actions
    "exclusively available" that way. Leaving fullscreen is the case that needs
    an on-screen affordance, because fullscreen has collapsed every other one.

    The KDE HIG sanctions the placement: a button "overlaid in a fixed
    'floating' position over a scrollable content view, especially an image
    view" (hig/getting_input.md), with "a contrasting outline around the edge"
    so it stays legible against a dark backdrop (hig/displaying_content.md).
    """

    # Distance from the corner of the view, and how faint it sits at rest
    MARGIN = 12
    RESTING_OPACITY = 0.55

    def __init__(self, parent, on_click):
        super().__init__(parent)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(22, 22))
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Leave fullscreen (Esc)")
        self.setStyleSheet(
            "QToolButton { border: 1px solid rgba(255, 255, 255, 60);"
            " border-radius: 18px; background: rgba(0, 0, 0, 130); color: white; }"
            "QToolButton:hover { background: rgba(0, 0, 0, 190); }"
        )

        icon = QIcon.fromTheme("view-restore")
        self.setIcon(icon)
        # Breeze may be absent (bare test environments, non-KDE sessions); an
        # empty round button would be an invisible control.
        self.setText("" if not icon.isNull() else "⛶")

        # Child widgets have no windowOpacity of their own; an opacity effect is
        # the only way to make one sit back without repainting it by hand.
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(self.RESTING_OPACITY)
        self.setGraphicsEffect(self._opacity)

        self.clicked.connect(on_click)

        # The button is a sibling of the view's viewport rather than a laid-out
        # widget, so nothing repositions it for us.
        parent.installEventFilter(self)
        self.hide()
        self.reposition()

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
        self.move(x, self.MARGIN)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self.reposition()
            self.raise_()
        return super().eventFilter(watched, event)

    def enterEvent(self, event):
        self._opacity.setOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._opacity.setOpacity(self.RESTING_OPACITY)
        super().leaveEvent(event)

    def setVisible(self, visible):
        super().setVisible(visible)
        if visible:
            self.reposition()
            self.raise_()
