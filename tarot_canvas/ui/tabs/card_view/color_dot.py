from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt

class ColorDot(QIcon):
    """Creates a colored dot icon for tab decoration"""
    def __init__(self, color):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 16, 16)  # Draw a circle with 8px diameter
        painter.end()
        
        super().__init__(pixmap)