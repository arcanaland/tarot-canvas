"""Tells views a note was written, renamed or deleted.

The card view owns every write; the library only reads. Without this the notes list would
either poll or go stale the moment a note is saved in a tab beside it.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class NoteEvents(QObject):
    notes_changed = pyqtSignal()


_instance = None


def note_events():
    global _instance
    if _instance is None:
        _instance = NoteEvents()
    return _instance
