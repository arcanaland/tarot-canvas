from PyQt6.QtCore import Qt

from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate


class SpreadRowDelegate(NoteRowDelegate):
    """A row in the spread library"""

    WELL_ASPECT = 1.0

    def _paint_well(self, painter, well, palette, index):
        index.data(Qt.ItemDataRole.DecorationRole).paint(painter, well)
