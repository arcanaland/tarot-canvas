"""The search field at the start of a page's header row"""

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QLineEdit


def search_field(placeholder):
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    field.addAction(QIcon.fromTheme("search"), QLineEdit.ActionPosition.LeadingPosition)
    return field
