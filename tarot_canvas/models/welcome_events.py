from PyQt6.QtCore import QObject, pyqtSignal


class WelcomeEvents(QObject):
    # Whether the window opens on the Welcome tab changed
    show_at_startup_changed = pyqtSignal(bool)


_instance = None


def welcome_events():
    global _instance
    if _instance is None:
        _instance = WelcomeEvents()
    return _instance
