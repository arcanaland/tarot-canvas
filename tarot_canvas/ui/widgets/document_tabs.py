"""The main window's tab widget."""

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QTabWidget

from tarot_canvas.ui.tabs.base_tab import BaseTab


class DocumentTabs(QTabWidget):
    def tabInserted(self, index):
        super().tabInserted(index)
        page = self.widget(index)
        if isinstance(page, BaseTab):
            self._label(index, page)
            page.tab_label_changed.connect(self._relabel_sender)

    @pyqtSlot()
    def _relabel_sender(self):
        page = self.sender()
        index = self.indexOf(page)
        if index >= 0:
            self._label(index, page)

    def _label(self, index, page):
        self.setTabText(index, page.tab_title())
        self.setTabIcon(index, page.tab_icon())
