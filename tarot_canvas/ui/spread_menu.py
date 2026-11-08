"""Every spread a reading can start from"""

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu

from tarot_canvas.models import spreads
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.icons import LIBRARY_ICON
from tarot_canvas.ui.library.spreads_model import spread_thumbnail, spread_title
from tarot_canvas.ui.strings import READINGS

# Blender's splash shows five templates; the rest are one click away in the Library
MAX_OWN = 5


def spread_menu(parent, start, browse):
    menu = QMenu(parent)
    menu.aboutToShow.connect(lambda: _fill(menu, start, browse))
    return menu


def sections():
    """The menu's (folder, Spread) rows, in sections, the user's first as in the Library"""
    # Smallest first, as the Library's slot-count sort: a single card leads
    included = sorted(
        spreads.scan_included(),
        key=lambda row: (len(row[1].positions), spread_title(row[1]).casefold()),
    )
    own = sorted(spreads.scan(), key=lambda row: spreads.edited_at(row[0]), reverse=True)
    return [rows for rows in (own[:MAX_OWN], included) if rows]


def _fill(menu, start, browse):
    menu.clear()
    unit = card_unit_size()
    for rows in sections():
        for path, spread in rows:
            action = menu.addAction(
                spread_thumbnail(spread, unit),
                spread_title(spread).replace("&", "&&"),  # a spread name is no mnemonic
            )
            action.triggered.connect(lambda _checked, path=path: start(path))
        menu.addSeparator()
    browse_action = menu.addAction(QIcon.fromTheme(LIBRARY_ICON), READINGS["browse_spreads"])
    browse_action.triggered.connect(browse)
