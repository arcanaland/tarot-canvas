from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene

class CanvasTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        # Create a canvas area for card placement
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        self.layout.addWidget(self.view)