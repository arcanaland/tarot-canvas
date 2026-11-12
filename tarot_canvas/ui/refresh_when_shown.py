"""A view that re-reads on a change only while it is shown, and once when it is next shown"""

from PyQt6.QtCore import QEvent, QObject, pyqtSlot


class RefreshWhenShown(QObject):
    """Calls refresh on changed while widget is visible; while it is hidden, a change only marks it
    stale, and the next Show refreshes once. A tab in the background then costs nothing per write,
    however many readings it lists."""

    def __init__(self, widget, refresh):
        super().__init__(widget)
        self._widget = widget
        self._refresh = refresh
        self.stale = False
        widget.installEventFilter(self)

    @pyqtSlot()
    def changed(self):
        if self._widget.isVisible():
            self._refresh()
        else:
            self.stale = True

    def eventFilter(self, watched, event):
        if watched is self._widget and event.type() == QEvent.Type.Show and self.stale:
            self.stale = False
            self._refresh()
        return False
