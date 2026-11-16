"""The item roles and sort keys every Library view answers, so no view imports another's model"""

from PyQt6.QtCore import Qt

# Each view's own roles stay in its model; these are the ones the shared row delegates read
SubtitleRole = Qt.ItemDataRole.UserRole + 2
CoverPathRole = Qt.ItemDataRole.UserRole + 3
PreviewRole = Qt.ItemDataRole.UserRole + 15
# Short text at a row's trailing end, before its buttons, or None for none
BadgeRole = Qt.ItemDataRole.UserRole + 16
# True on a heading row. A model answers it and gives the row no flags, so it is never selected
SectionRole = Qt.ItemDataRole.UserRole + 40
# Whether the user pinned the row (curation, in models.library_curation)
PinnedRole = Qt.ItemDataRole.UserRole + 41
# Whether the row is drawn faded: a hidden spread a search or Show brought back
DimmedRole = Qt.ItemDataRole.UserRole + 42
# True on a quiet row that does something when clicked or Entered, rather than being an item
ToggleRole = Qt.ItemDataRole.UserRole + 43

SORT_NAME = "name"
SORT_COUNT = "count"

SELECTED_SUBTITLE_ALPHA = 200
