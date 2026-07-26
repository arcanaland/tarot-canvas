from pathlib import Path

from PyQt6.QtGui import QIcon


class CanvasIcon(QIcon):
    """Creates an icon for canvas tab decoration using a Breeze icon"""

    def __init__(self):
        # Use the draw-rectangle icon from Breeze theme (or fallback to local path)
        icon = QIcon.fromTheme(
            "draw-rectangle",
            QIcon(
                str(
                    Path(__file__).parent.parent.parent
                    / "resources"
                    / "icons"
                    / "draw-rectangle.png"
                )
            ),
        )
        super().__init__(icon)
