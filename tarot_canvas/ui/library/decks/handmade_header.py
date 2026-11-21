"""A handmade deck's header: its fields edited where they stand, its Cards choice and actions"""

import itertools

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.library.decks.header import HeaderFrame, measure
from tarot_canvas.ui.library.decks.model import (
    fill_progress,
    is_majors_only,
    placed_minors,
)
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.widgets.inline_editors import InlineLineEdit, InlineTextEdit


class CardsChoice(QWidget):
    """Majors only or all 78, as deck.toml has it"""

    chosen = pyqtSignal(bool)  # all 78, or majors only

    def __init__(self, parent=None):
        super().__init__(parent)
        self._whole = False
        self._deck = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(units.LARGE_SPACING)
        label = QLabel(DECK_VIEW["cards_label"])
        row.addWidget(label)
        self.majors_radio = QRadioButton(DECK_VIEW["cards_majors_only"])
        self.all_radio = QRadioButton(DECK_VIEW["cards_all"])
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for button in (self.majors_radio, self.all_radio):
            self.group.addButton(button)
            row.addWidget(button)
        label.setBuddy(self.majors_radio)
        self.group.buttonClicked.connect(self._on_clicked)
        row.addStretch()

    def show_deck(self, deck):
        self._deck = deck
        self._whole = not is_majors_only(deck)
        self.majors_radio.setChecked(not self._whole)
        self.all_radio.setChecked(self._whole)
        self.setEnabled(True)

    def _on_clicked(self, button):
        whole = button is self.all_radio
        if whole == self._whole:
            return
        if not whole and not self._confirm_majors_only():
            self.show_deck(self._deck)
            return
        # Until the reload, so a second click can't queue a second write
        self.setEnabled(False)
        self.chosen.emit(whole)

    def _confirm_majors_only(self):
        """Ask before placed minors go to unsorted/; nothing to ask when none are"""
        count = placed_minors(self._deck)
        if not count:
            return True
        box = QMessageBox(self.window())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(DECK_VIEW["majors_only_title"])
        box.setText(
            DECK_VIEW["majors_only_text_one"]
            if count == 1
            else DECK_VIEW["majors_only_text"].format(count=count)
        )
        confirm = box.addButton(
            DECK_VIEW["majors_only_confirm"], QMessageBox.ButtonRole.DestructiveRole
        )
        box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Cancel))
        box.exec()
        return box.clickedButton() is confirm


class FillProgress(QWidget):
    """How many of the deck's cards have an image"""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(units.LARGE_SPACING)
        self.label = QLabel()
        typography.apply(self.label, typography.Role.SMALL)
        row.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(units.SMALL_SPACING * 2)
        self.bar.setMaximumWidth(measure() // 3)
        row.addWidget(self.bar, 1)
        row.addStretch(2)

    def show_deck(self, deck):
        placed, expected = fill_progress(deck)
        self.label.setText(DECK_VIEW["fill_count"].format(placed=placed, expected=expected))
        self.bar.setRange(0, max(1, expected))
        self.bar.setValue(placed)


class HandmadeDeckHeader(HeaderFrame):
    """Always open: name, artist, description, the Cards choice and the fill; actions top right"""

    fields_edited = pyqtSignal(dict)  # [deck] key: new text, "" to remove it
    add_images_requested = pyqtSignal()
    cards_chosen = pyqtSignal(bool)  # all 78, or majors only

    def __init__(self, deck, parent=None, cover_cache=None):
        super().__init__(deck, parent, cover_cache)
        self.text_container.setLayout(self._build_column())
        # Down the column, then the action row
        order = [
            self.name_edit,
            self.artist_edit,
            self.description_edit,
            self.cards.majors_radio,
            self.cards.all_radio,
            self.add_images_button,
        ]
        for first, second in itertools.pairwise(order):
            QWidget.setTabOrder(first, second)
        self._align_column()
        self.cover.set_expanded(True)
        self.align_text(top=True)
        self.update_from(deck)

    def _build_column(self):
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(units.SMALL_SPACING)

        title_row = QHBoxLayout()
        title_row.setSpacing(units.LARGE_SPACING)
        self.name_edit = self._editor(InlineLineEdit(), "field.name")
        typography.apply(self.name_edit, typography.Role.HEADING_1, primary=True)
        self.name_edit.committed.connect(self._on_name_committed)
        title_row.addWidget(self.name_edit, 1, Qt.AlignmentFlag.AlignTop)
        title_row.addStretch()

        # Export… joins it here
        self.actions = QHBoxLayout()
        self.actions.setSpacing(units.SMALL_SPACING)
        self.add_images_button = QPushButton(QIcon.fromTheme("list-add"), DECK_VIEW["add_images"])
        self.add_images_button.clicked.connect(self.add_images_requested)
        self.actions.addWidget(self.add_images_button, 0, Qt.AlignmentFlag.AlignTop)
        title_row.addLayout(self.actions)
        title_row.setAlignment(self.actions, Qt.AlignmentFlag.AlignTop)
        column.addLayout(title_row)

        self.artist_edit = self._editor(InlineLineEdit(), "field.artist", "artist_placeholder")
        typography.apply(self.artist_edit, typography.Role.SMALL)
        self.artist_edit.committed.connect(lambda text: self._commit("artist", text))
        column.addWidget(self.artist_edit)

        self.description_edit = self._editor(
            InlineTextEdit(), "field.description", "description_placeholder"
        )
        self.description_edit.committed.connect(lambda text: self._commit("description", text))
        column.addWidget(self.description_edit)

        column.addSpacing(units.SMALL_SPACING)
        self.cards = CardsChoice()
        self.cards.chosen.connect(self.cards_chosen)
        column.addWidget(self.cards)
        self.fill = FillProgress()
        column.addWidget(self.fill)
        column.addStretch()
        return column

    def _align_column(self):
        """Everything down the column starts where the editors' text does"""
        editors = (self.name_edit, self.artist_edit, self.description_edit)
        inset = max(editor.natural_inset() for editor in editors)
        for editor in editors:
            editor.set_text_inset(inset)
        for row in (self.cards, self.fill):
            row.layout().setContentsMargins(inset, 0, 0, 0)

    @staticmethod
    def _editor(editor, name, placeholder=None):
        editor.setAccessibleName(DECK_VIEW[name])
        if placeholder is not None:
            editor.setPlaceholderText(DECK_VIEW[placeholder])
        editor.setMaximumWidth(measure())
        return editor

    def _on_name_committed(self, text):
        name = text.strip()
        if not name:
            self.name_edit.revert()
            return
        self.name_edit.setText(name)
        self._commit("name", name)

    def _commit(self, key, text):
        text = text.strip()
        editor = {
            "name": self.name_edit,
            "artist": self.artist_edit,
            "description": self.description_edit,
        }[key]
        if text == editor.saved():
            return
        editor.set_saved(text)
        self.fields_edited.emit({key: text})

    def update_from(self, deck):
        """Show deck, reloaded, without disturbing an editor being typed in"""
        self.deck = deck
        metadata = deck.metadata
        self.name_edit.set_saved(metadata.name or "")
        self.artist_edit.set_saved(metadata.artist or "")
        self.description_edit.set_saved(metadata.description or "")
        self.cards.show_deck(deck)
        self.fill.show_deck(deck)
        self.cover.set_deck(deck)
