from PyQt6.QtCore import QObject, pyqtSignal


class EsotericaEvents(QObject):
    # Which families are open or hidden changed
    display_changed = pyqtSignal()
    # The set of sources, or which of them are enabled, changed
    sources_changed = pyqtSignal()


_instance = None


def esoterica_events():
    global _instance
    if _instance is None:
        _instance = EsotericaEvents()
    return _instance
