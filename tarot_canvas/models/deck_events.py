"""Tells views the set of installed decks has changed."""

from PyQt6.QtCore import QObject, pyqtSignal


class DeckEvents(QObject):
    decks_changed = pyqtSignal()


_instance = None


def deck_events():
    global _instance
    if _instance is None:
        _instance = DeckEvents()
    return _instance
