"""Tells views the set of installed decks has changed.

DeckManager isn't a QObject, so its notifications live here. The instance is
made on first use, never at import.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class DeckEvents(QObject):
    decks_changed = pyqtSignal()


_instance = None


def deck_events():
    global _instance
    if _instance is None:
        _instance = DeckEvents()
    return _instance
