from PyQt6.QtCore import QKeyCombination, Qt
from PyQt6.QtGui import QKeySequence

from tarot_canvas.ui.commands import keys_for

# Keys that a keypad or a layout switch adds to an event
_IGNORED_MODIFIERS = Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier


# The registry's, so that the art, which takes these keys itself, follows View > Zoom
def zoom_in_keys():
    return keys_for("window.zoom_in")


def zoom_out_keys():
    return keys_for("window.zoom_out")


def reset_zoom_keys():
    return keys_for("window.reset_zoom")


def matches(event, keys):
    """Whether a key event is one of `keys`, with or without the Shift its character needed"""
    modifiers = event.modifiers() & ~_IGNORED_MODIFIERS
    key = Qt.Key(event.key())
    pressed = [
        QKeySequence(QKeyCombination(modifiers, key)),
        QKeySequence(QKeyCombination(modifiers & ~Qt.KeyboardModifier.ShiftModifier, key)),
    ]
    return any(sequence in pressed for sequence in keys)
