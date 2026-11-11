from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QToolButton


class ExpandButton(QToolButton):
    """A flat button that gives a pane more room, or gives it back"""

    def __init__(self, expand_tip, restore_tip):
        super().__init__()
        self.setAutoRaise(True)
        self._tips = (expand_tip, restore_tip)

    def sync(self, shown, expanded):
        self.setVisible(shown)
        self.setIcon(QIcon.fromTheme("view-restore" if expanded else "view-fullscreen"))
        tooltip = self._tips[1] if expanded else self._tips[0]
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
