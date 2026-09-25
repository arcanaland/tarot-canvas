from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QListView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.library import units
from tarot_canvas.ui.notes_text import text
from tarot_canvas.ui.widgets.placeholder_message import PlaceholderMessage

EMPTY_ICON = "story-editor"


class NotesEmptyPage(QWidget):
    """A card with nothing written on it"""

    def __init__(self, helpful_action, parent=None):
        super().__init__(parent)
        self.placeholder = PlaceholderMessage(
            EMPTY_ICON, text("empty_heading"), helpful_action=helpful_action
        )

        layout = QVBoxLayout(self)
        margin = units.GRID_UNIT
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addStretch(1)
        layout.addWidget(self.placeholder)
        layout.addStretch(1)


class NotesListPage(QWidget):
    """A card's notes, one row each, under a New Note button"""

    def __init__(self, model, delegate, new_note_action, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, units.SMALL_SPACING, 0, 0)
        layout.setSpacing(units.SMALL_SPACING)

        # The tab's label already says Notes, so the header is only its add button
        header = QHBoxLayout()
        header.setContentsMargins(units.LARGE_SPACING, 0, units.LARGE_SPACING, 0)
        header.addStretch()

        self.new_button = QToolButton()
        self.new_button.setDefaultAction(new_note_action)
        self.new_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.new_button.setAutoRaise(True)
        header.addWidget(self.new_button)

        layout.addLayout(header)

        self.view = QListView()
        self.view.setModel(model)
        self.view.setItemDelegate(delegate)
        self.view.setUniformItemSizes(True)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.view)
