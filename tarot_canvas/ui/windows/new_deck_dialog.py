from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from tarot_canvas.ui.strings import NEW_DECK


class NewDeckDialog(QDialog):
    """A name, and all 78 cards or the majors only"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(NEW_DECK["title"])

        self.name_field = QLineEdit()
        self.all_cards = QRadioButton(NEW_DECK["all_cards"])
        self.majors = QRadioButton(NEW_DECK["majors_only"])
        self.all_cards.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.all_cards)
        group.addButton(self.majors)

        form = QFormLayout()
        form.addRow(NEW_DECK["name"], self.name_field)
        form.addRow("", self.all_cards)
        form.addRow("", self.majors)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.create_button = self.buttons.addButton(
            NEW_DECK["create"], QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.create_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

        self.name_field.textChanged.connect(self._update_create)
        self._update_create()

    def _update_create(self):
        self.create_button.setEnabled(bool(self.name().strip()))

    def name(self):
        return self.name_field.text()

    def majors_only(self):
        return self.majors.isChecked()
