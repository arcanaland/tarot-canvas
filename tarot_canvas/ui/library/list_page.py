from PyQt6.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListView,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.library.deselect import deselect_on_empty_click_or_escape


class LibraryListPage(QWidget):
    """A Library view that is a list, with its details pane below it in the tab"""

    details_changed = pyqtSignal()

    def __init__(self, list_model, delegate_class, details_pane, parent=None):
        super().__init__(parent)
        self.list_model = list_model
        self.list_model.setParent(self)
        self.list_view = self._build_list(delegate_class)

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setEnabled(False)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.list_view, 1)
        column.addWidget(self.empty_label)

        self.details_pane = details_pane

    def _build_list(self, delegate_class):
        view = QListView()
        view.setModel(self.list_model)
        self.row_delegate = delegate_class(view)
        view.setItemDelegate(self.row_delegate)

        view.setViewMode(QListView.ViewMode.ListMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setAlternatingRowColors(True)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setMouseTracking(True)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        view.activated.connect(self._on_activated)
        activate_on_return(view)
        view.clicked.connect(self._show_details)
        view.selectionModel().currentChanged.connect(self._on_current_changed)
        deselect_on_empty_click_or_escape(view)
        return view

    # -- what the library asks of a page ----------------------------------

    def search_placeholder(self):
        raise NotImplementedError

    def details_toggle_tooltip(self, is_open):
        raise NotImplementedError

    def set_search(self, text):
        self.list_model.set_search(text)
        self._update_empty_state()

    # -- what a page fills in -----------------------------------------------

    def _empty_text(self, searching):
        raise NotImplementedError

    def _details_for(self, index):
        """The details pane's contents for a row, or None"""
        raise NotImplementedError

    def _on_activated(self, index):
        raise NotImplementedError

    # -- selection --------------------------------------------------------

    def _select_index(self, index):
        if not index.isValid():
            return False
        self.list_view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        return True

    def _on_current_changed(self, current, _previous):
        if current.isValid():
            self._show_details(current)

    def _show_details(self, index):
        self._show(self._details_for(index))

    def _show(self, details):
        if details is not None:
            self.details_pane.show_details(details)
            self.details_changed.emit()

    def _update_empty_state(self):
        empty = not self.list_model.has_items()
        if empty:
            self.empty_label.setText(self._empty_text(bool(self.list_model.search())))
        self.empty_label.setVisible(empty and bool(self.empty_label.text()))
        self.list_view.setVisible(not empty)
