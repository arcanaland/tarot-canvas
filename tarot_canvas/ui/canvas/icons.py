from PyQt6.QtGui import QIcon


class CanvasIcon(QIcon):
    """Creates an icon for canvas tab decoration using a Breeze icon"""

    def __init__(self):
        super().__init__(QIcon.fromTheme("draw-rectangle"))
