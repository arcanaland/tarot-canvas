from tarot_canvas.ui.library.section_row import SectionedRowDelegate
from tarot_canvas.ui.strings import READINGS


class ReadingRowDelegate(SectionedRowDelegate):
    """A row in the Journal, with its menu button, or the heading of a month"""

    def __init__(self, parent=None, cover_cache=None):
        super().__init__(
            parent,
            cover_cache,
            menu_button=True,
            menu_tooltip=READINGS["library_menu_tooltip"],
        )
