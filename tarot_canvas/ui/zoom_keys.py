from PyQt6.QtCore import QKeyCombination, Qt
from PyQt6.QtGui import QKeySequence

# Keys that a keypad or a layout switch adds to an event
_IGNORED_MODIFIERS = Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier


def zoom_in_keys():
    keys = list(QKeySequence.keyBindings(QKeySequence.StandardKey.ZoomIn))
    # + shares a key with = on many layouts, so the unshifted press zooms too
    equals = QKeySequence("Ctrl+=")
    if equals not in keys:
        keys.append(equals)
    return keys


def zoom_out_keys():
    return list(QKeySequence.keyBindings(QKeySequence.StandardKey.ZoomOut))


def reset_zoom_keys():
    return [QKeySequence("Ctrl+0")]


def matches(event, keys):
    """Whether a key event is one of `keys`, with or without the Shift its character needed"""
    modifiers = event.modifiers() & ~_IGNORED_MODIFIERS
    key = Qt.Key(event.key())
    pressed = [
        QKeySequence(QKeyCombination(modifiers, key)),
        QKeySequence(QKeyCombination(modifiers & ~Qt.KeyboardModifier.ShiftModifier, key)),
    ]
    return any(sequence in pressed for sequence in keys)
