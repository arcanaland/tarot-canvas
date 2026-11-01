from PyQt6.QtCore import QObject, pyqtSignal


class SpreadEvents(QObject):
    spreads_changed = pyqtSignal()


_instance = None


def spread_events():
    global _instance
    if _instance is None:
        _instance = SpreadEvents()
    return _instance
