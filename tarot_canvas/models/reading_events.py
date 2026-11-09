from PyQt6.QtCore import QObject, pyqtSignal


class ReadingEvents(QObject):
    readings_changed = pyqtSignal()


_instance = None


def reading_events():
    global _instance
    if _instance is None:
        _instance = ReadingEvents()
    return _instance
