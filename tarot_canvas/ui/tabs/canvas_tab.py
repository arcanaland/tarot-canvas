from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtWidgets import QToolBar, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QPixmap, QBrush, QPen, QColor, QPainter

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.deck_manager import deck_manager
import os

class DraggableCardItem(QGraphicsPixmapItem):
    """A draggable card item for the canvas."""
    
    def __init__(self, pixmap, card_data, parent_tab=None):
        super().__init__(pixmap)
        self.card_data = card_data
        self.parent_tab = parent_tab
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        
        # Set a border when selected
        self.setPen = QPen(QColor(255, 215, 0))  # Gold color
        self.setPen.setWidth(3)
        
    def paint(self, painter, option, widget):
        # Call the parent class's paint method first
        super().paint(painter, option, widget)
        
        # If selected, draw a border
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 215, 0), 3))  # Gold border, 3px width
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.boundingRect().adjusted(1, 1, -1, -1))  # Adjust rect to fit inside
    
    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, 'open_card_view'):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)

class CanvasTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)  # action, data
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.id = f"canvas_{id(self)}"  # Unique ID for this tab
        self.setup_ui()        
        self.deck = deck_manager.get_reference_deck()
        
        # Navigation history
        self.source_tab = None  # From where we came
    
    def setup_ui(self):
        # Create a container widget instead of using self directly
        container = QWidget()
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Minimize padding
        main_layout.setSpacing(0)
        
        # Create a canvas area for card placement
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(QRectF(0, 0, 2000, 2000))  # Large canvas area
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setBackgroundBrush(QBrush(QColor(120, 120, 120)))  # Light gray background
        
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
            # TODO: add icons with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
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

    def on_draw_card(self):
        """Draw a random card and add it to the canvas"""
        if not self.deck:
            print("No deck loaded!")
            return
            
        # Get a random card
        card = self.deck.get_random_card()
        if not card:
            print("Could not draw a card!")
            return
            
        # Load the card image
        image_path = card.get("image")
        if not image_path or not os.path.exists(image_path):
            print(f"Card image not found: {image_path}")
            return
            
        try:
            # Create a pixmap from the card image
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                print(f"Failed to load image: {image_path}")
                return
                
            # Scale the pixmap to a reasonable size if needed
            if pixmap.width() > 300 or pixmap.height() > 500:
                pixmap = pixmap.scaled(300, 500, Qt.AspectRatioMode.KeepAspectRatio, 
                                      Qt.TransformationMode.SmoothTransformation)
                
            # Create a draggable card item - pass self as parent_tab
            card_item = DraggableCardItem(pixmap, card, self)
            
            # Position the card in the middle of the visible canvas
            view_center = self.view.mapToScene(self.view.viewport().rect().center())
            card_item.setPos(view_center.x() - pixmap.width()/2, 
                            view_center.y() - pixmap.height()/2)
            
            # Add the card to the scene
            self.scene.addItem(card_item)
            
            # Select the newly added card
            card_item.setSelected(True)
            
            print(f"Added card: {card['name']}")
            
        except Exception as e:
            print(f"Error adding card to canvas: {e}")
            
    def open_card_view(self, card_data):
        """Open a card view tab for the given card"""
        self.navigation_requested.emit("open_card_view", {
            "card": card_data,
            "deck": self.deck,
            "source_tab_id": self.id
        })
    
    def on_create_spread(self):
        # Implement creating a new spread
        pass

    def on_clear_canvas(self):
        # Implement clearing the canvas
        self.scene.clear()

    def on_save_layout(self):
        # Implement saving the layout
        pass
    
    def on_navigate_back(self):
        """Navigate back to the source tab"""
        if self.source_tab:
            self.navigation_requested.emit("navigate", self.source_tab)