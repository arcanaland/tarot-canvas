from PyQt6.QtCore import QSize, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

DEFAULT_WIDTH = 320


class SidePane(QScrollArea):
    """A collapsible panel on the right of a splitter"""

    # The user or the code opened or collapsed it
    open_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        self.body = QVBoxLayout(body)
        self.setWidget(body)

        self.splitter = None
        self._open_width = DEFAULT_WIDTH

    def sizeHint(self):
        return QSize(DEFAULT_WIDTH, super().sizeHint().height())

    def dock(self, splitter):
        """Become the last pane of splitter, which keeps any extra width for the others"""
        self.splitter = splitter
        splitter.addWidget(self)
        last = splitter.count() - 1
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(last, 0)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(last, True)
        splitter.splitterMoved.connect(self._on_splitter_moved)

    def is_open(self):
        return self.splitter.sizes()[-1] > 0

    def set_open(self, wanted):
        if wanted == self.is_open():
            return
        sizes = self.splitter.sizes()
        total = sum(sizes)
        if wanted:
            self.splitter.setSizes([max(0, total - self._open_width), self._open_width])
        else:
            self._open_width = sizes[-1]
            self.splitter.setSizes([total, 0])
        self.open_changed.emit(wanted)

    @pyqtSlot()
    def _on_splitter_moved(self):
        if self.is_open():
            self._open_width = self.splitter.sizes()[-1]
        self.open_changed.emit(self.is_open())
