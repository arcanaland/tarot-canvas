from PyQt6.QtCore import QModelIndex, QPoint, pyqtSignal

from tarot_canvas.ui.library.note_row_delegate import RowButton
from tarot_canvas.ui.library.section_row import SectionedRowDelegate
from tarot_canvas.ui.strings import READINGS, SPREADS


class SpreadRowDelegate(SectionedRowDelegate):
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
