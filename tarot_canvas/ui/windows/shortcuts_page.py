"""The Preferences page that lists every command's keys and edits them"""

from PyQt6.QtCore import QEvent, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QHeaderView,
    QKeySequenceEdit,
    QLineEdit,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import commands
from tarot_canvas.ui.commands import COMMANDS, Scope
from tarot_canvas.ui.library import units
from tarot_canvas.ui.notes_text import NOTES_TEXT
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.ui.windows.preferences_text import PREFERENCES_TEXT

GROUPS = (
    ("shortcuts_global", (Scope.WINDOW,)),
    ("shortcuts_canvas", (Scope.CANVAS,)),
    ("shortcuts_card", (Scope.CARD, Scope.CARD_IMAGE)),
    ("shortcuts_notes", (Scope.NOTES,)),
    ("shortcuts_library", (Scope.LIBRARY,)),
)

COMMAND_ROLE = Qt.ItemDataRole.UserRole
KEY_ROLE = Qt.ItemDataRole.UserRole + 1

# Shortcut and Alternate
CELLS = 2


def label(command):
    """A command's text without its mnemonic or the key after a tab"""
    text = (command.text or "").split("\t")[0]
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def listed_commands():
    """Every command with a key of its own, in registry order"""
    return [command for command in COMMANDS if not command.shows]


def key_cells(keys):
    """The first two keys, padded with empty ones"""
    return (tuple(keys[:CELLS]) + ("",) * CELLS)[:CELLS]


class _GroupsShownByChildren(QSortFilterProxyModel):
    """Filters commands; a group is shown while any of its commands is"""

    def filterAcceptsRow(self, row, parent):
        if not parent.isValid():
            return False
        return super().filterAcceptsRow(row, parent)


class _KeyDelegate(QStyledItemDelegate):
    """Edits a key cell with a one-key QKeySequenceEdit, handing the result to propose"""

    def __init__(self, propose, parent=None):
        super().__init__(parent)
        self.propose = propose

    def createEditor(self, parent, option, index):
        editor = QKeySequenceEdit(parent)
        editor.setMaximumSequenceLength(1)
        editor.setClearButtonEnabled(True)
        editor.editingFinished.connect(lambda: self._finish(editor))
        # Only its clear button edits the text; a key press sets it
        editor.findChild(QLineEdit).textEdited.connect(lambda: self._finish(editor))
        return editor

    def _finish(self, editor):
        # Already closed by a click elsewhere
        if not editor.isVisible():
            return
        # Closing it moves its focus, which would finish it again
        editor.blockSignals(True)
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def setEditorData(self, editor, index):
        blocked = editor.blockSignals(True)
        editor.setKeySequence(
            QKeySequence.fromString(
                index.data(KEY_ROLE) or "", QKeySequence.SequenceFormat.PortableText
            )
        )
        editor.blockSignals(blocked)

    def setModelData(self, editor, model, index):
        self.propose(model.mapToSource(index), editor.keySequence())

    def eventFilter(self, editor, event):
        # Every key is one to record, Esc, Tab and Return included
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            return False
        return super().eventFilter(editor, event)


class ShortcutsPage(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Command id to its keys as the page has them, in portable text
        self.keys = {}
        self.cells = {}

        self.model = QStandardItemModel(0, 1 + CELLS, self)
        self.model.setHorizontalHeaderLabels(
            [
                PREFERENCES_TEXT["shortcuts_action"],
                PREFERENCES_TEXT["shortcuts_primary"],
                PREFERENCES_TEXT["shortcuts_alternate"],
            ]
        )
        for group_key, scopes in GROUPS:
            group = [QStandardItem(PREFERENCES_TEXT[group_key])]
            group += [QStandardItem() for _ in range(CELLS)]
            for item in group:
                item.setEditable(False)
            for command in listed_commands():
                if command.scope in scopes:
                    group[0].appendRow(self._command_row(command))
            self.model.appendRow(group)

        self.proxy = _GroupsShownByChildren(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(PREFERENCES_TEXT["shortcuts_search"])
        self.search.textChanged.connect(self.filter)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setUniformRowHeights(True)
        self.tree.setItemDelegate(_KeyDelegate(self.propose, self.tree))
        self.tree.setEditTriggers(
            QTreeView.EditTrigger.DoubleClicked
            | QTreeView.EditTrigger.SelectedClicked
            | QTreeView.EditTrigger.EditKeyPressed
        )
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 1 + CELLS):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(column, 7 * units.GRID_UNIT)
        self.tree.expandAll()

        self.message = InlineMessage(close_text=NOTES_TEXT["dismiss"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.message)

    def _command_row(self, command):
        name = QStandardItem(label(command))
        if command.icon:
            name.setIcon(QIcon.fromTheme(command.icon))
        name.setData(command.id, COMMAND_ROLE)
        name.setEditable(False)
        cells = [QStandardItem() for _ in range(CELLS)]
        row = [name, *cells]
        for item in cells:
            item.setEditable(not command.fixed)
        if command.fixed:
            for item in row:
                item.setEnabled(False)
        self.cells[command.id] = cells
        return row

    def filter(self, text):
        self.proxy.setFilterFixedString(text)
        self.tree.expandAll()

    def show_keys(self, keys):
        """Show each command's keys, given as {id: keys}"""
        self.keys = {command_id: commands.portable(k) for command_id, k in keys.items()}
        for command_id in self.keys:
            self._show(command_id)
        self.message.hide()
        self.changed.emit()

    def _show(self, command_id):
        for item, key in zip(self.cells[command_id], key_cells(self.keys[command_id]), strict=True):
            item.setData(key, KEY_ROLE)
            item.setText(
                QKeySequence.fromString(key, QKeySequence.SequenceFormat.PortableText).toString(
                    QKeySequence.SequenceFormat.NativeText
                )
            )

    def load(self):
        self.show_keys({c.id: commands.keys_for(c.id) for c in listed_commands()})

    def reset(self):
        self.show_keys({c.id: commands.default_keys(c.id) for c in listed_commands()})

    def apply(self):
        for command_id, keys in self.keys.items():
            commands.store_keys(command_id, keys)
        commands.apply_shortcuts()

    def state(self):
        return tuple(self.keys.items())

    def propose(self, index, sequence):
        """Take a key for a cell, unless a command that could fire with it holds it"""
        command_id = self.model.itemFromIndex(index.siblingAtColumn(0)).data(COMMAND_ROLE)
        if command_id is None:
            return
        cells = list(key_cells(self.keys[command_id]))
        key = commands.portable([sequence])[0] if not sequence.isEmpty() else ""
        if key == cells[index.column() - 1]:
            return
        self.message.hide()

        if commands.by_id(command_id).scope is Scope.WINDOW and commands.is_bare_letter_or_digit(
            sequence
        ):
            native = sequence.toString(QKeySequence.SequenceFormat.NativeText)
            self.message.show_message(PREFERENCES_TEXT["shortcuts_bare"].format(key=native))
            return

        cells[index.column() - 1] = key
        keys = tuple(dict.fromkeys(cell for cell in cells if cell))
        for clash, holder, other in commands.conflicts({**self.keys, command_id: keys}):
            if clash == key and command_id in (holder, other):
                owner = commands.by_id(other if holder == command_id else holder)
                self.message.show_message(
                    PREFERENCES_TEXT["shortcuts_taken"].format(command=label(owner))
                )
                return

        self.keys[command_id] = keys
        self._show(command_id)
        self.changed.emit()
