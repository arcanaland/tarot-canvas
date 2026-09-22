from PyQt6.QtCore import QObject, pyqtSignal


class NoteEvents(QObject):
    notes_changed = pyqtSignal()


_instance = None


def note_events():
    global _instance
    if _instance is None:
        _instance = NoteEvents()
    return _instance
