from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtProperty


class CardAnimationController(QObject):
    """Controller for card animations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotation = 0.0
        self._scale = 1.0
        self.card_item = None

    def _live_card_item(self):
        """Stub to handle if the card was deleted on the C++ side"""
        if self.card_item is None:
            return None
        if sip.isdeleted(self.card_item):
            self.card_item = None
            return None
        return self.card_item

    def _get_rotation(self):
        return self._rotation

    def _set_rotation(self, angle):
        self._rotation = angle
        item = self._live_card_item()
        if item is not None:
            item.setRotation(angle)

    def _get_scale(self):
        return self._scale

    def _set_scale(self, scale):
        self._scale = scale
        item = self._live_card_item()
        if item is not None:
            item.setScale(scale)

    # Define properties for QPropertyAnimation
    rotation = pyqtProperty(float, _get_rotation, _set_rotation)
    scale = pyqtProperty(float, _get_scale, _set_scale)
