from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtWidgets import QToolBar, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction

class CanvasTab(BaseTab):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        # Create a container widget instead of using self directly
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Minimize padding
        main_layout.setSpacing(0)
        
        # Create a canvas area for card placement
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        # Add canvas to layout (will take most of the space)
        main_layout.addWidget(self.view, 1)  # The 1 is stretch factor
        
        # Create toolbar on the right
        self.create_toolbar(main_layout)
        
        # Set up the base layout (assuming BaseTab has one)
        # This depends on how BaseTab is implemented
        if hasattr(self, 'layout') and callable(getattr(self.layout, 'addWidget', None)):
            self.layout.addWidget(container)
        else:
            # If BaseTab doesn't have a layout, create one
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(container)
    
    def create_toolbar(self, parent_layout):
        # Create a vertical layout for the toolbar
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setSpacing(10)
        toolbar_layout.setContentsMargins(5, 10, 5, 10)
        
        # Create a widget to hold the toolbar
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar_layout)
        toolbar_widget.setFixedWidth(80)  # Fixed width for the toolbar
        
        # Create toolbar actions
        actions = [
            ("Draw Card", "draw_card", "Draw a random card"),
            ("Create Spread", "create_spread", "Create a new card spread"),
            ("Clear Canvas", "clear_canvas", "Clear all cards from canvas"),
            ("Save Layout", "save_layout", "Save the current layout"),
        ]
        
        # Add actions to toolbar
        for name, icon_name, tooltip in actions:
            action = QAction(name, self)
            # You can add icons later with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
            action.setToolTip(tooltip)
            
            # Create button for the action
            button = QPushButton(name)
            button.setToolTip(tooltip)
            button.setMinimumHeight(40)
            
            # Connect to placeholder methods (implement these later)
            if icon_name == "draw_card":
                button.clicked.connect(self.on_draw_card)
            elif icon_name == "create_spread":
                button.clicked.connect(self.on_create_spread)
            elif icon_name == "clear_canvas":
                button.clicked.connect(self.on_clear_canvas)
            elif icon_name == "save_layout":
                button.clicked.connect(self.on_save_layout)
                
            toolbar_layout.addWidget(button)
        
        # Add spacer to push buttons to the top
        toolbar_layout.addStretch()
        
        # Add the toolbar to the main layout
        parent_layout.addWidget(toolbar_widget, 0)  # The 0 means no stretch

    # Placeholder methods for toolbar actions
    def on_draw_card(self):
        # Implement drawing a random card
        pass

    def on_create_spread(self):
        # Implement creating a new spread
        pass

    def on_clear_canvas(self):
        # Implement clearing the canvas
        self.scene.clear()

    def on_save_layout(self):
        # Implement saving the layout
        pass