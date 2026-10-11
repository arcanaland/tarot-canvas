from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QLabel


def pane_text(text=""):
    """A details pane's label: plain, since deck.toml, the index and a source are someone
    else's text, and wrapped and selectable"""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def pane_form():
    """A details pane's form. Its fields take the pane's width: Breeze keeps them at their size
    hint, which gives a wrapped value one line's height and cuts off the rest."""
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form
