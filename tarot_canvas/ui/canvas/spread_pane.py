from PyQt6.QtCore import QSignalBlocker, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.side_pane import SidePane
from tarot_canvas.ui.strings import SPREADS

USAGE_LINES = 4
MEANING_LINES = 6


def _text_box(hint, lines):
    box = QPlainTextEdit()
    box.setPlaceholderText(hint)
    box.setTabChangesFocus(True)
    box.setFixedHeight(box.fontMetrics().lineSpacing() * lines + 2 * box.frameWidth() + 8)
    return box


def _heading(text):
    label = QLabel(text)
    typography.apply(label, typography.Role.HEADING_4)
    return label


class SourceRow(QWidget):
    """One source: its url, author and note"""

    changed = pyqtSignal()
    remove_requested = pyqtSignal()

    FIELDS = ("url", "author", "note")

    def __init__(self, source=None, parent=None):
        super().__init__(parent)
        self.source = source or {}
        self.edits = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        fields = QVBoxLayout()
        layout.addLayout(fields, 1)
        for key in self.FIELDS:
            edit = QLineEdit(str(self.source.get(key, "")))
            edit.setPlaceholderText(SPREADS[f"source_{key}_hint"])
            edit.textChanged.connect(self.changed)
            fields.addWidget(edit)
            self.edits[key] = edit

        self.remove_button = QToolButton()
        self.remove_button.setIcon(QIcon.fromTheme("list-remove"))
        self.remove_button.setToolTip(SPREADS["remove_source"])
        self.remove_button.clicked.connect(self.remove_requested)
        layout.addWidget(self.remove_button)

    def value(self):
        """The source as a table, keeping any keys this row doesn't show"""
        kept = {key: value for key, value in self.source.items() if key not in self.FIELDS}
        typed = {key: edit.text().strip() for key, edit in self.edits.items()}
        return {**kept, **{key: text for key, text in typed.items() if text}}


class SpreadPane(SidePane):
    """A spread's name, use and sources, and its slots or the selected slot"""

    name_edited = pyqtSignal()
    # Anything here that the file keeps
    edited = pyqtSignal()
    label_edited = pyqtSignal(str)
    meaning_edited = pyqtSignal(str)
    slot_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(SPREADS["name_hint"])
        self.name_edit.textChanged.connect(self.name_edited)
        self.name_edit.textChanged.connect(self.edited)
        self.body.addWidget(_heading(SPREADS["name_title"]))
        self.body.addWidget(self.name_edit)

        self.usage_edit = _text_box(SPREADS["usage_hint"], USAGE_LINES)
        self.usage_edit.textChanged.connect(self.edited)
        self.body.addWidget(_heading(SPREADS["usage_title"]))
        self.body.addWidget(self.usage_edit)

        self.source_rows = []
        self.sources_layout = QVBoxLayout()
        self.add_source_button = QPushButton(QIcon.fromTheme("list-add"), SPREADS["add_source"])
        self.add_source_button.clicked.connect(lambda: self.add_source_row())
        self.body.addWidget(_heading(SPREADS["sources_title"]))
        self.body.addLayout(self.sources_layout)
        self.body.addWidget(self.add_source_button)

        self.slot_heading = _heading(SPREADS["slots_title"])
        self.body.addWidget(self.slot_heading)

        self.slot_editor = QWidget()
        editor_layout = QVBoxLayout(self.slot_editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText(SPREADS["label_hint"])
        self.label_edit.textChanged.connect(self.label_edited)
        self.meaning_edit = _text_box(SPREADS["meaning_hint"], MEANING_LINES)
        self.meaning_edit.textChanged.connect(self._on_meaning_edited)
        editor_layout.addWidget(self.label_edit)
        editor_layout.addWidget(self.meaning_edit)
        self.body.addWidget(self.slot_editor)

        self.slot_list = QListWidget()
        self.slot_list.itemClicked.connect(
            lambda item: self.slot_clicked.emit(self.slot_list.row(item))
        )
        self.body.addWidget(self.slot_list)

        self.body.addStretch(1)
        self.show_slots(())

    # -- the spread --------------------------------------------------------

    def name(self):
        return self.name_edit.text().strip()

    def set_name(self, name):
        self.name_edit.setText(name)

    def usage(self):
        return self.usage_edit.toPlainText()

    def sources(self):
        return tuple(value for row in self.source_rows if (value := row.value()))

    def set_document(self, name, usage, sources):
        self.set_name(name)
        self.usage_edit.setPlainText(usage)
        for source in sources:
            self.add_source_row(source)

    def add_source_row(self, source=None):
        row = SourceRow(source)
        row.changed.connect(self.edited)
        row.remove_requested.connect(self._remove_sender)
        self.source_rows.append(row)
        self.sources_layout.addWidget(row)
        return row

    @pyqtSlot()
    def _remove_sender(self):
        row = self.sender()
        self.source_rows.remove(row)
        self.sources_layout.removeWidget(row)
        row.deleteLater()
        self.edited.emit()

    # -- the slots ---------------------------------------------------------

    def show_slot(self, number, label, meaning):
        """Edit one slot"""
        self.slot_heading.setText(SPREADS["slot_title"].format(number=number))
        with QSignalBlocker(self.label_edit):
            self.label_edit.setText(label)
        with QSignalBlocker(self.meaning_edit):
            self.meaning_edit.setPlainText(meaning)
        self.slot_list.hide()
        self.slot_editor.show()

    def show_slots(self, rows):
        """List (number, label) rows"""
        self.slot_heading.setText(SPREADS["slots_title"])
        self.slot_list.clear()
        self.slot_list.addItems(
            SPREADS["slot_row"].format(number=number, label=label) for number, label in rows
        )
        self.slot_editor.hide()
        self.slot_list.show()

    def focus_label(self):
        self.label_edit.setFocus()
        self.label_edit.selectAll()

    def focus_meaning(self):
        self.meaning_edit.setFocus()

    @pyqtSlot()
    def _on_meaning_edited(self):
        self.meaning_edited.emit(self.meaning_edit.toPlainText())
