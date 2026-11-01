from PyQt6.QtWidgets import QLineEdit

from tarot_canvas.ui import typography


def heading_edit(placeholder):
    """A name set as a page's heading, which is typed over where it stands"""
    edit = QLineEdit()
    edit.setFrame(False)
    edit.setPlaceholderText(placeholder)
    typography.apply(edit, typography.Role.HEADING_2)
    return edit
