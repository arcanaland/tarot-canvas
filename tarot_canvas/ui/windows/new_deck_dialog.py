from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QVBoxLayout,
)

from tarot_canvas.ui import units
from tarot_canvas.ui.strings import NEW_DECK

# The name field's width, in average characters
NAME_WIDTH = 40


class NewDeckDialog(QDialog):
    """Asks for the new deck's name, and nothing else"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(NEW_DECK["title"])

        explanation = QLabel(NEW_DECK["explanation"])
        explanation.setWordWrap(True)

        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText(NEW_DECK["name_placeholder"])
        self.name_field.setMinimumWidth(
            self.name_field.fontMetrics().averageCharWidth() * NAME_WIDTH
        )

        form = QFormLayout()
        form.addRow(NEW_DECK["name"], self.name_field)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.create_button = self.buttons.addButton(
            NEW_DECK["create"], QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.create_button.setIcon(QIcon.fromTheme("document-new"))
        self.create_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(units.LARGE_SPACING * 2)
        layout.addWidget(explanation)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        # A fixed size, so the window manager offers no maximize
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.name_field.textChanged.connect(self._update_create)
        self._update_create()

    def _update_create(self):
        self.create_button.setEnabled(bool(self.name().strip()))

    def name(self):
        return self.name_field.text()
