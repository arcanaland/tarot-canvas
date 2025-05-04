from PyQt6.QtCore import QObject, pyqtProperty

class CardAnimationController(QObject):
    """Controller for card animations."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotation = 0.0
        self._scale = 1.0
        self.card_item = None
    
    def _get_rotation(self):
        return self._rotation
        
    def _set_rotation(self, angle):
        self._rotation = angle
        if self.card_item:
            self.card_item.setRotation(angle)
        
    def _get_scale(self):
        return self._scale
        
    def _set_scale(self, scale):
        self._scale = scale
        if self.card_item:
            self.card_item.setScale(scale)
    
    # Define properties for QPropertyAnimation
    rotation = pyqtProperty(float, _get_rotation, _set_rotation)
    scale = pyqtProperty(float, _get_scale, _set_scale)