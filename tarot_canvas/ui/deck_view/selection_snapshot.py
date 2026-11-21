"""A view's current card and selection, by slot ID, so they survive a view switch or a reload"""

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex

from tarot_canvas.ui.deck_view.card_model import SlotIdRole


class SelectionSnapshot:
    def __init__(self, current, selected):
        self.current = current  # a slot ID, or None
        self.selected = selected  # slot IDs

    @classmethod
    def take(cls, view):
        current = view.currentIndex().data(SlotIdRole)
        selected = {index.data(SlotIdRole) for index in view.selectionModel().selectedIndexes()}
        selected.discard(None)
        return cls(current, selected)

    def restore(self, view):
        """Onto view, whose model may be another view's, or reset since; slots gone are skipped"""
        selection = QItemSelection()
        for slot in self.selected:
            index = _index_of(view, slot)
            if index.isValid():
                selection.select(index, index)
        selection_model = view.selectionModel()
        target = _index_of(view, self.current) if self.current is not None else QModelIndex()
        selection_model.setCurrentIndex(target, QItemSelectionModel.SelectionFlag.NoUpdate)
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)


def _index_of(view, slot):
    model = view.model()
    cards = model.sourceModel()
    row = cards.row_of(slot)
    return QModelIndex() if row is None else model.mapFromSource(cards.index(row, 0))
