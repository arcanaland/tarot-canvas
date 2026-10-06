from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from tarot_canvas.ui.tabs.card_view.passage_metrics import HEADING_TO_BODY


class Fold(QWidget):
    """A header that shows or hides the content under it"""

    toggled = pyqtSignal(bool)

    def __init__(self, text, content, expanded=False, parent=None):
        super().__init__(parent)
        self.header = QToolButton()
        self.header.setText(text)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setAutoRaise(True)
        self.header.setCheckable(True)
        self.content = content

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(HEADING_TO_BODY)
        layout.addWidget(self.header)
        layout.addWidget(content)

        self._show(expanded)
        self.header.toggled.connect(self._on_toggled)

    def is_expanded(self):
        return self.header.isChecked()

    def _show(self, expanded):
        self.header.setChecked(expanded)
        self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)

    def _on_toggled(self, expanded):
        self._show(expanded)
        self.toggled.emit(expanded)
