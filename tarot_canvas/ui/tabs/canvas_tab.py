from tarot_canvas.ui.tabs.base_tab import BaseTab
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
from PyQt6.QtWidgets import QToolBar, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QIcon, QAction, QPixmap, QBrush, QPen, QColor, QPainter, QTransform
import types
from PyQt6.QtGui import QUndoStack, QUndoCommand, QRadialGradient, QKeySequence, QLinearGradient
from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QPointF
from PyQt6.QtCore import QSequentialAnimationGroup, QParallelAnimationGroup, pyqtProperty, QObject
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.deck_manager import deck_manager
import os
import random
import math

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


class DraggableCardItem(QGraphicsPixmapItem):
    """Enhanced draggable card item with wobble animation."""
    
    def __init__(self, pixmap, card_data, parent_tab=None):
        super().__init__(pixmap)
        self.card_data = card_data
        self.parent_tab = parent_tab
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)

        # Create animation controller
        self.anim_controller = CardAnimationController()
        self.anim_controller.card_item = self
        
        # Set up wobble animation
        self.setup_wobble_animation()
        
    def setup_wobble_animation(self):
        """Set up wobble animation with slight rotation changes."""
        # Create a sequential animation group for rotation
        self.rotation_anim = QSequentialAnimationGroup()

        # Create subtle rotation animations
        rot1 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot1.setDuration(4000 + random.randint(-500, 500))  # Randomize duration slightly
        rot1.setStartValue(0)
        rot1.setEndValue(0.8)  # Small rotation angle
        rot1.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot2 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot2.setDuration(2000 + random.randint(-500, 500))
        rot2.setStartValue(0.8)
        rot2.setEndValue(-0.8)  # Small negative rotation
        rot2.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot3 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot3.setDuration(2000 + random.randint(-500, 500))
        rot3.setStartValue(-0.8)
        rot3.setEndValue(0)  # Back to neutral
        rot3.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        # Add the animations to the sequence
        self.rotation_anim.addAnimation(rot1)
        self.rotation_anim.addAnimation(rot2)
        self.rotation_anim.addAnimation(rot3)
        
        # Create a very subtle scale animation
        
        self.scale_anim = QPropertyAnimation(self.anim_controller, b"scale")
        self.scale_anim.setDuration(1500 + random.randint(-300, 300))
        self.scale_anim.setStartValue(1.0)
        self.scale_anim.setEndValue(1.02)  # Very slight scale up
        self.scale_anim.setLoopCount(-1)  # Loop indefinitely
        self.scale_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        # Start animations with slight delay for each card
        QTimer.singleShot(random.randint(0, 1000), self.start_animations)
        
    def start_animations(self):
        """Start the wobble animations."""
        self.rotation_anim.setLoopCount(-1)  # Loop indefinitely
        self.rotation_anim.start()
        #self.scale_anim.start()
        
    def pause_animations(self):
        """Pause animations (when card is being dragged)."""
        self.rotation_anim.pause()
        self.scale_anim.pause()
        
    def resume_animations(self):
        """Resume animations after dragging stops."""
        self.rotation_anim.resume()
        self.scale_anim.resume()
        
    # Override these to pause/resume animations during drag
    def mousePressEvent(self, event):
        self.pause_animations()
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Small delay before resuming animation
        QTimer.singleShot(200, self.resume_animations)
        
    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, 'open_card_view'):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)

# Create a custom QGraphicsView to handle shift+drag panning
class PannableGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._panning = False
        self._last_mouse_pos = None
        
    def mousePressEvent(self, event):
        """Override mouse press to implement shift+drag panning"""
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Start panning mode
            self._panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            # Default behavior (selection)
            super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        """Handle mouse movement for panning or default behavior"""
        if self._panning and self._last_mouse_pos:
            # Calculate how much to pan
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()
            
            # Pan the view
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            
            event.accept()
        else:
            super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release for ending panning or default behavior"""
        if self._panning:
            self._panning = False
            self._last_mouse_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event):
        """Handle zooming with mouse wheel"""
        zoom_factor = 1.15
        
        if event.angleDelta().y() > 0:
            # Zoom in
            self.scale(zoom_factor, zoom_factor)
        else:
            # Zoom out
            self.scale(1.0 / zoom_factor, 1.0 / zoom_factor)


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
        #background = AnimatedBackground(self.scene.sceneRect())
        #self.scene.addItem(background)
        # Use our custom view with shift+drag panning
        self.view = PannableGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor(120, 120, 120)))  # Gray background
        
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
        
        # Set up keyboard shortcuts
        self.setup_shortcuts()
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts for common actions"""
        # Create shortcut for Draw Card (d key)
        draw_shortcut = QKeySequence("d")
        draw_action = QAction("Draw Card", self)
        draw_action.setShortcut(draw_shortcut)
        draw_action.triggered.connect(self.on_draw_card)
        self.addAction(draw_action)
        
        # Create shortcut for Delete (Delete/Backspace keys)
        delete_shortcut = QKeySequence(Qt.Key.Key_Delete)
        delete_action = QAction("Delete Card", self)
        delete_action.setShortcut(delete_shortcut)
        delete_action.triggered.connect(self.on_delete_card)
        self.addAction(delete_action)
        
        # Add backspace as an alternative delete key
        backspace_shortcut = QKeySequence(Qt.Key.Key_Backspace)
        backspace_action = QAction("Delete Card (Backspace)", self)
        backspace_action.setShortcut(backspace_shortcut)
        backspace_action.triggered.connect(self.on_delete_card)
        self.addAction(backspace_action)
    
    def create_toolbar(self, parent_layout):
        # Create a vertical layout for the toolbar
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setSpacing(10)
        toolbar_layout.setContentsMargins(5, 10, 5, 10)
        
        # Create a widget to hold the toolbar
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar_layout)
        toolbar_widget.setFixedWidth(80)  # Fixed width for the toolbar
        
        # Primary actions for the first section of toolbar
        primary_actions = [
            ("Draw Card", "draw_card", "Draw a random card"),
            ("Rotate", "rotate_card", "Rotate selected card"),
            ("Flip", "flip_card", "Flip selected card"),
            ("Duplicate", "duplicate_card", "Clone selected card"),
            ("Delete", "delete_card", "Remove selected card"),
        ]
        
        # Add primary actions to toolbar
        for name, icon_name, tooltip in primary_actions:
            action = QAction(name, self)
            # TODO: add icons with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
            action.setToolTip(tooltip)
            
            # Create button for the action
            button = QPushButton(name)
            button.setToolTip(tooltip)
            button.setMinimumHeight(40)
            
            # Connect the primary action buttons
            if icon_name == "draw_card":
                button.clicked.connect(self.on_draw_card)
            elif icon_name == "rotate_card":
                button.clicked.connect(self.on_rotate_card)
            elif icon_name == "flip_card":
                button.clicked.connect(self.on_flip_card)
            elif icon_name == "duplicate_card":
                button.clicked.connect(self.on_duplicate_card)
            elif icon_name == "delete_card":
                button.clicked.connect(self.on_delete_card)
                
            toolbar_layout.addWidget(button)
        
        # Add a section divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(divider)
        
        # Arrangement actions
        arrangement_actions = [
            ("To Front", "bring_to_front", "Bring card to front"),
            ("To Back", "send_to_back", "Send card to back"),
            ("Lock", "toggle_lock", "Lock/unlock selected card"),
            ("Group", "toggle_group", "Group/ungroup selected cards"),
            ("Align", "align_cards", "Align selected cards"),
        ]
        
        # Add arrangement actions to toolbar
        for name, icon_name, tooltip in arrangement_actions:
            action = QAction(name, self)
            # TODO: add icons with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
            action.setToolTip(tooltip)
            
            # Create button for the action
            button = QPushButton(name)
            button.setToolTip(tooltip)
            button.setMinimumHeight(40)
            
            # Connect the arrangement action buttons
            if icon_name == "bring_to_front":
                button.clicked.connect(self.on_bring_to_front)
            elif icon_name == "send_to_back":
                button.clicked.connect(self.on_send_to_back)
            elif icon_name == "toggle_lock":
                button.clicked.connect(self.on_toggle_lock)
            elif icon_name == "toggle_group":
                button.clicked.connect(self.on_toggle_group)
            elif icon_name == "align_cards":
                button.clicked.connect(self.on_align_cards)
                
            toolbar_layout.addWidget(button)
        
        # Add another section divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(divider)
        
        # Tarot-specific actions
        tarot_actions = [
            ("Spreads", "choose_spread", "Select a tarot spread template"),
            ("Highlight", "highlight_card", "Highlight/emphasize card"),
            ("Connect", "connect_cards", "Draw connections between cards"),
            ("Add Item", "add_object", "Add gem, stone or other object"),
        ]
        
        # Add tarot-specific actions to toolbar
        for name, icon_name, tooltip in tarot_actions:
            action = QAction(name, self)
            # TODO: add icons with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
            action.setToolTip(tooltip)
            
            # Create button for the action
            button = QPushButton(name)
            button.setToolTip(tooltip)
            button.setMinimumHeight(40)
            
            # Connect the tarot action buttons
            if icon_name == "choose_spread":
                button.clicked.connect(self.on_choose_spread)
            elif icon_name == "highlight_card":
                button.clicked.connect(self.on_highlight_card)
            elif icon_name == "connect_cards":
                button.clicked.connect(self.on_connect_cards)
            elif icon_name == "add_object":
                button.clicked.connect(self.on_add_object)
                
            toolbar_layout.addWidget(button)
        
        # Add another section divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(divider)
        
        # View control actions
        view_actions = [
            ("Zoom In", "zoom_in", "Zoom in"),
            ("Zoom Out", "zoom_out", "Zoom out"),
            ("Fit View", "fit_view", "Fit all cards in view"),
            ("Reset View", "reset_view", "Reset to default view"),
            ("Grid", "toggle_grid", "Show/hide grid"),
        ]
        
        # Add view control actions to toolbar
        for name, icon_name, tooltip in view_actions:
            action = QAction(name, self)
            # TODO: add icons with: action.setIcon(QIcon("path/to/icons/{icon_name}.png"))
            action.setToolTip(tooltip)
            
            # Create button for the action
            button = QPushButton(name)
            button.setToolTip(tooltip)
            button.setMinimumHeight(40)
            
            # Connect the view action buttons
            if icon_name == "zoom_in":
                button.clicked.connect(self.on_zoom_in)
            elif icon_name == "zoom_out":
                button.clicked.connect(self.on_zoom_out)
            elif icon_name == "fit_view":
                button.clicked.connect(self.on_fit_view)
            elif icon_name == "reset_view":
                button.clicked.connect(self.on_reset_view)
            elif icon_name == "toggle_grid":
                button.clicked.connect(self.on_toggle_grid)
                
            toolbar_layout.addWidget(button)
        
        # Add another section divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar_layout.addWidget(divider)
        
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
            # Deselect any currently selected cards
            for selected_item in self.scene.selectedItems():
                selected_item.setSelected(False)
                
            # Get the center of the viewport
            view_center = self.view.mapToScene(self.view.viewport().rect().center())
            
            # Add a slight random offset (±50 pixels) to avoid exact center placement
            offset_x = random.randint(-50, 50)
            offset_y = random.randint(-50, 50)
            view_center = QPointF(view_center.x() + offset_x, view_center.y() + offset_y)
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
    
    # Canvas Control Methods
    def on_zoom_in(self):
        """Zoom into the canvas"""
        self.view.scale(1.2, 1.2)
    
    def on_zoom_out(self):
        """Zoom out of the canvas"""
        self.view.scale(0.8, 0.8)
    
    def on_fit_view(self):
        """Fit all items in view"""
        # Get bounding rect of all items
        items = self.scene.items()
        if not items:
            return
        # Calculate bounding rect of all items
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        # Add margin
        rect.adjust(-50, -50, 50, 50)
        # Fit view to rect
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
    
    def on_reset_view(self):
        """Reset view to default position and zoom"""
        self.view.resetTransform()
        self.view.centerOn(self.scene.sceneRect().center())
    
    def toggle_pan_mode(self):
        """Toggle between pan mode and selection mode"""
        if self.view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    # Card Manipulation Methods
    def on_rotate_card(self):
        """Rotate the selected card by 90 degrees"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                item.setRotation((item.rotation() + 90) % 360)
            
    def on_flip_card(self):
        """Flip the selected card horizontally (to indicate reversed)"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                # Apply a scale transform to flip
                item.setTransform(QTransform().scale(-1, 1), True)
            
    def on_duplicate_card(self):
        """Duplicate the selected card"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                # Create a copy of the card
                new_item = DraggableCardItem(item.pixmap(), item.card_data, self)
                # Position it slightly offset from the original
                new_item.setPos(item.pos() + QPointF(20, 20))
                new_item.setRotation(item.rotation())
                # Add to scene
                self.scene.addItem(new_item)
            
    def on_delete_card(self):
        """Remove the selected card from canvas"""
        items = self.scene.selectedItems()
        for item in items:
            self.scene.removeItem(item)
        
    def on_toggle_lock(self):
        """Lock or unlock the selected card"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                # Toggle movable flag
                is_movable = item.flags() & QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable
                if is_movable:
                    item.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable, False)
                else:
                    item.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable, True)

    # Arrangement Control Methods
    def on_bring_to_front(self):
        """Bring selected card to front"""
        items = self.scene.selectedItems()
        for item in items:
            item.setZValue(100)  # High z-value
        
    def on_send_to_back(self):
        """Send selected card to back"""
        items = self.scene.selectedItems()
        for item in items:
            item.setZValue(-100)  # Low z-value
        
    def on_toggle_group(self):
        """Group or ungroup selected cards"""
        items = self.scene.selectedItems()
        if not items or len(items) < 2:
            return
        
        # Here we would implement grouping logic
        # Could create a QGraphicsItemGroup or custom implementation
        pass
    
    def on_align_cards(self):
        """Show alignment options for selected cards"""
        # This could open a small popup with alignment options:
        # - Align left, center, right
        # - Align top, middle, bottom
        # - Distribute horizontally/vertically
        pass

    # Grid and Guidelines
    def on_toggle_grid(self):
        """Toggle grid visibility"""
        # Implement grid drawing logic
        # Could be stored as a scene background or drawn on paintEvent
        self.show_grid = not getattr(self, 'show_grid', False)
        self.view.viewport().update()
    
    def setup_grid_drawing(self):
        """Set up grid drawing for the view"""
        # Override the view's drawBackground method
        old_draw_background = self.view.drawBackground
        
        def new_draw_background(painter, rect):
            # Call original method
            old_draw_background(painter, rect)
            
            # Draw grid if enabled
            if getattr(self, 'show_grid', False):
                # Draw grid lines
                painter.setPen(QPen(QColor(80, 80, 80, 100), 1))
                grid_size = 50
                
                # Calculate visible area
                left = int(rect.left()) - (int(rect.left()) % grid_size)
                top = int(rect.top()) - (int(rect.top()) % grid_size)
                
                # Draw vertical lines
                x = left
                while x < rect.right():
                    painter.drawLine(x, rect.top(), x, rect.bottom())
                    x += grid_size
                    
                # Draw horizontal lines
                y = top
                while y < rect.bottom():
                    painter.drawLine(rect.left(), y, rect.right(), y)
                    y += grid_size
        
        # Replace the drawBackground method
        self.view.drawBackground = types.MethodType(new_draw_background, self.view)

    # Tarot-Specific Features
    def on_choose_spread(self):
        """Show spread template options"""
        # This could open a dialog with spread options:
        # - Three-card spread
        # - Celtic Cross
        # - etc.
        pass
    
    def apply_spread_template(self, spread_name):
        """Apply a specific spread template"""
        if spread_name == "three_card":
            # Set up positions for a three-card spread
            positions = [
                QPointF(400, 500),  # Past
                QPointF(650, 500),  # Present
                QPointF(900, 500),  # Future
            ]
            # Draw cards for each position
            for pos in positions:
                self.draw_card_at_position(pos)
        elif spread_name == "celtic_cross":
            # Define positions for Celtic Cross
            pass
        
    def draw_card_at_position(self, position):
        """Draw a card and place it at a specific position"""
        if not self.deck:
            return
        
        card = self.deck.get_random_card()
        if not card:
            return
        
        # Create card item (simplified version of on_draw_card)
        pixmap = QPixmap(card.get("image"))
        if pixmap.isNull():
            return
        
        card_item = DraggableCardItem(pixmap, card, self)
        card_item.setPos(position)
        self.scene.addItem(card_item)
        return card_item
    
    def on_highlight_card(self):
        """Highlight or emphasize the selected card"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                # Toggle highlight state
                item.highlighted = not getattr(item, 'highlighted', False)
                # Update appearance
                item.update()
            
    def on_connect_cards(self):
        """Enable connection drawing mode between cards"""
        # Store state
        self.drawing_connection = not getattr(self, 'drawing_connection', False)
        self.connection_start_item = None
        
        # Update cursor
        if self.drawing_connection:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
    
    def on_add_object(self):
        """Add a gem, stone, seal or other object to the canvas"""
        # This could show a palette of available objects
        # Then the selected object is added to the canvas
        pass

    # Advanced Features
    def setup_undo_framework(self):
        """Set up undo/redo framework"""
        self.undo_stack = QUndoStack(self)
        
        # Add undo/redo actions to app menu
        undo_action = self.undo_stack.createUndoAction(self)
        redo_action = self.undo_stack.createRedoAction(self)
        
        # You would add these actions to a menu
        # menu.addAction(undo_action)
        # menu.addAction(redo_action)
    
class CardMoveCommand(QUndoCommand):
    """Undo command for card movements"""
    def __init__(self, item, old_pos, new_pos):
        super().__init__()
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos
        self.setText(f"Move {item.card_data.get('name', 'Card')}")
        
    def undo(self):
        self.item.setPos(self.old_pos)
        
    def redo(self):
        self.item.setPos(self.new_pos)