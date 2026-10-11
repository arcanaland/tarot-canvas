from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QLabel


def pane_text(text=""):
    """A details pane's label"""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def pane_form():
    """A details pane's form."""
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form
