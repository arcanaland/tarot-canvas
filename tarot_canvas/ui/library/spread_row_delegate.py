from PyQt6.QtCore import QModelIndex, QPoint, pyqtSignal

from tarot_canvas.ui.library.note_row_delegate import IconRowDelegate, RowButton
from tarot_canvas.ui.library.section_row import is_section, paint_section, section_size_hint
from tarot_canvas.ui.strings import READINGS, SPREADS


class SpreadRowDelegate(IconRowDelegate):
    """A row in the spread library, or the heading of a section of them"""

    # The row, and where its button is (unused)
    readingRequested = pyqtSignal(QModelIndex, QPoint)

    def __init__(self, parent=None, cover_cache=None):
        super().__init__(
            parent,
            cover_cache,
            buttons=(
                RowButton(
                    "media-playback-start",
                    READINGS["open"],
                    "readingRequested",
                    command="library.start_reading",
                ),
            ),
            menu_button=True,
            menu_tooltip=SPREADS["menu_tooltip"],
        )

    def sizeHint(self, option, index):
        if is_section(index):
            return section_size_hint()
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        if is_section(index):
            paint_section(painter, option, index)
            return
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if is_section(index):
            return False
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        if is_section(index):
            return False
        return super().helpEvent(event, view, option, index)
