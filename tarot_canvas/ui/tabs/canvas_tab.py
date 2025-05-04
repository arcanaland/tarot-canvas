from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QToolBar, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QFrame, QSizePolicy, QApplication, QLabel
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QSequentialAnimationGroup, QParallelAnimationGroup, pyqtProperty, QObject, QSize
from PyQt6.QtGui import QIcon, QAction, QPixmap, QBrush, QPen, QColor, QPainter, QTransform, QUndoStack, QUndoCommand, QRadialGradient, QKeySequence, QLinearGradient

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab

import types
import os
import random
import math
from pathlib import Path

class CanvasIcon(QIcon):
    """Creates an icon for canvas tab decoration using a Breeze icon"""
    def __init__(self):
        # Use the draw-rectangle icon from Breeze theme (or fallback to local path)
        icon = QIcon.fromTheme("draw-rectangle", 
                  QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "draw-rectangle.png")))
        super().__init__(icon)

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
        
    def setup_wobble_animation(self, base_rotation=0):
        """Set up wobble animation with slight rotation changes."""
        # Stop any existing animation
        if hasattr(self, 'rotation_anim') and self.rotation_anim:
            self.rotation_anim.stop()
        
        # Create a sequential animation group for rotation
        self.rotation_anim = QSequentialAnimationGroup()

        # Create subtle rotation animations around the base rotation
        rot1 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot1.setDuration(4000 + random.randint(-500, 500))  # Randomize duration slightly
        rot1.setStartValue(base_rotation)
        rot1.setEndValue(base_rotation + 0.8)  # Small rotation angle
        rot1.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot2 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot2.setDuration(2000 + random.randint(-500, 500))
        rot2.setStartValue(base_rotation + 0.8)
        rot2.setEndValue(base_rotation - 0.8)  # Small negative rotation
        rot2.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot3 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot3.setDuration(2000 + random.randint(-500, 500))
        rot3.setStartValue(base_rotation - 0.8)
        rot3.setEndValue(base_rotation)  # Back to neutral
        rot3.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        # Add the animations to the sequence
        self.rotation_anim.addAnimation(rot1)
        self.rotation_anim.addAnimation(rot2)
        self.rotation_anim.addAnimation(rot3)
        
        # Create a very subtle scale animation (keep this part the same)
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
        self.tab_name = "Canvas"  # Default tab name
        
        # Set a size policy that doesn't try to expand vertically
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Add a maximum size constraint to prevent excessive expansion
        self.setMaximumHeight(800)  # Set a reasonable maximum height
        
        # Setup the UI with size-constrained components
        self.setup_ui()        
        self.deck = deck_manager.get_reference_deck()
        
        # Navigation history
        self.source_tab = None  # From where we came
        
        # Add multiple staggered calls to ensure window bounds
        # This creates a sequence of enforcement that is harder to override
        QTimer.singleShot(100, self.ensure_window_bounds)
        QTimer.singleShot(500, self.ensure_window_bounds)
        QTimer.singleShot(1000, self.ensure_window_bounds)
        
        # Set the canvas tab icon
        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        # Create a container widget instead of using self directly
        container = QWidget()
        main_layout = QHBoxLayout(container)
        
        # Remove all margins to eliminate the padding
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create a canvas area for card placement with sensible size constraints
        self.scene = QGraphicsScene(self)
        
        # Set a more conservative scene rect size 
        self.scene.setSceneRect(QRectF(-500, -500, 1000, 1000))
        
        # Use our custom view with shift+drag panning
        self.view = PannableGraphicsView(self.scene)
        
        # Create and set the purple checkerboard background
        self.create_purple_checkerboard_background()
        
        # Adjust height constraints to be less restrictive
        # Remove the maximum height constraint that may be causing the padding
        
        # Set sensible sizing policies for the view
        # Use Expanding for both directions to fill available space
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Maintain minimum size to prevent collapse
        self.view.setMinimumSize(400, 300)
        
        # Set view behavior that doesn't auto-expand
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add canvas to layout (will take most of the space)
        main_layout.addWidget(self.view, 1)
        
        # Create toolbar on the right
        self.create_toolbar(main_layout)
        
        # Simplify the layout structure and remove potential padding sources
        # Set up the base layout (assuming BaseTab has one)
        if hasattr(self, 'layout'):
            # Clear any existing layout contents
            while self.layout.count():
                item = self.layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
                    
            # Reset margins to zero
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.addWidget(container)
        else:
            # If BaseTab doesn't have a layout, create one
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(container)
        
        # Set up keyboard shortcuts
        self.setup_shortcuts()
    
    def create_purple_checkerboard_background(self):
        """Create a purple checkerboard pattern background for the canvas"""
        # Define two purple colors for the checkerboard
        light_purple = QColor(220, 210, 240)  # Light lavender
        dark_purple = QColor(180, 160, 220)   # Darker lavender
        
        # Create a pixmap for the pattern
        size = 50  # Size of each square
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Create a painter to draw the pattern
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Draw the checkerboard pattern
        painter.setBrush(QBrush(light_purple))
        painter.drawRect(0, 0, size, size)
        painter.drawRect(size, size, size, size)
        
        painter.setBrush(QBrush(dark_purple))
        painter.drawRect(0, size, size, size)
        painter.drawRect(size, 0, size, size)
        
        painter.end()
        
        # Create a brush with this pattern
        pattern_brush = QBrush(pixmap)
        
        # Set the background brush of the view
        self.view.setBackgroundBrush(pattern_brush)
    
    def ensure_window_bounds(self):
        """Ensure the window stays within screen boundaries"""
        window = self.window()
        if window:
            # Get screen geometry
            screen = QApplication.primaryScreen().availableGeometry()

            # Get window geometry
            window_geometry = window.geometry()

            # Check if window extends below screen
            if window_geometry.height() > screen.height() - 50:  # Leave 50px margin
                # Force a hard resize
                new_height = screen.height() - 100  # 100px margin for safety
                
                # Block signals temporarily to prevent resize events from triggering cascading changes
                window.blockSignals(True)
                window.resize(window_geometry.width(), new_height)
                window.blockSignals(False)
                
                print(f"Window height exceeds screen height - forcing resize to {new_height}")
                
                # Process events immediately to apply resize
                QApplication.processEvents()
            
            # Do a second check after processing events
            window_geometry = window.geometry()
            if window_geometry.bottom() > screen.bottom() - 50:
                # If still too tall, try a different approach - move to visible area
                print("Window still too tall, applying stronger constraints")
                
                # Move window to ensure it's within screen bounds
                new_y = max(screen.top(), screen.bottom() - window_geometry.height() - 50)
                window.move(window_geometry.x(), new_y)
                
                # Force immediate processing
                QApplication.processEvents()
                
                # As a last resort, modify maximum size of main window
                window.setMaximumHeight(screen.height() - 100)
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts for all toolbar actions"""
        # Card Actions
        self.create_shortcut("D", self.on_draw_card, "Summon Card")
        self.create_shortcut("R", self.on_flip_card, "Flip Card (Reversed)")
        self.create_shortcut("Ctrl+D", self.on_duplicate_card, "Duplicate Card")
        self.create_shortcut(Qt.Key.Key_Delete, self.on_delete_card, "Delete Card")
        self.create_shortcut(Qt.Key.Key_Backspace, self.on_delete_card, "Delete Card (Alt)")
        
        # Arrangement Actions
        self.create_shortcut("Ctrl+]", self.on_bring_to_front, "Bring to Front")
        self.create_shortcut("Ctrl+[", self.on_send_to_back, "Send to Back")
        self.create_shortcut("Ctrl+A", self.on_align_cards, "Align Cards")
        
        # View Actions
        self.create_shortcut("Ctrl++", self.on_zoom_in, "Zoom In")
        self.create_shortcut("Ctrl+=", self.on_zoom_in, "Zoom In (Alt)")
        self.create_shortcut("Ctrl+-", self.on_zoom_out, "Zoom Out")
        self.create_shortcut("Ctrl+0", self.on_reset_view, "Reset View")
        self.create_shortcut("Ctrl+F", self.on_fit_view, "Fit All in View")
        
        # Navigation
        self.create_shortcut("Escape", self.on_escape_pressed, "Cancel Selection")

    def create_shortcut(self, key_sequence, slot, description=""):
        """Create and register a keyboard shortcut"""
        # Convert string to QKeySequence if needed
        if isinstance(key_sequence, str):
            shortcut = QKeySequence(key_sequence)
        else:
            shortcut = QKeySequence(key_sequence)
        
        # Create the action
        action = QAction(description, self)
        action.setShortcut(shortcut)
        action.triggered.connect(slot)
        self.addAction(action)
        
        # Update tooltip for corresponding toolbar button if it exists
        for toolbar_action in self.toolbar.actions():
            if toolbar_action.text() or toolbar_action.toolTip():
                # Check if this action is connected to the same slot
                # This is a bit of a hack but should work for simple cases
                connections = toolbar_action.receivers(toolbar_action.triggered)
                if connections > 0 and slot.__name__ in toolbar_action.toolTip():
                    # Update tooltip to include shortcut
                    current_tooltip = toolbar_action.toolTip().split(" (")[0]  # Remove any existing shortcut info
                    toolbar_action.setToolTip(f"{current_tooltip} ({shortcut.toString()})")
        
        return action

    def on_escape_pressed(self):
        """Handle Escape key - cancel selection"""
        # Clear any selection
        for item in self.scene.selectedItems():
            item.setSelected(False)
    
    def create_toolbar(self, parent_layout):
        """Create a vertical toolbar using QToolBar"""
        # Create a QToolBar configured for vertical layout
        self.toolbar = QToolBar()
        self.toolbar.setOrientation(Qt.Orientation.Vertical)
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        
        # Primary actions group
        self.toolbar.addWidget(self.create_section_label("Cards"))
        
        # Primary actions with Breeze icons
        primary_actions = [
            ("format-add-node", self.on_draw_card, "Summon a random card (D)"),
            ("object-flip-vertical", self.on_flip_card, "Flip card upside down (reversed position)"),
            ("edit-copy", self.on_duplicate_card, "Clone selected card"),
            ("edit-delete", self.on_delete_card, "Remove selected card (Delete)"),
        ]
        
        # Add primary actions to toolbar
        for icon_name, slot, tooltip in primary_actions:
            action = QAction(QIcon.fromTheme(icon_name, 
                            QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / f"{icon_name}.png"))),
                            "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
        
        # Arrangement actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label("Arrange"))
        
        # Arrangement actions with Breeze icons
        arrangement_actions = [
            ("go-top", self.on_bring_to_front, "Bring card to front"),
            ("go-bottom", self.on_send_to_back, "Send card to back"),
            ("align-horizontal-center", self.on_align_cards, "Align selected cards"),
        ]
        
        # Add arrangement actions to toolbar
        for icon_name, slot, tooltip in arrangement_actions:
            action = QAction(QIcon.fromTheme(icon_name, 
                            QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / f"{icon_name}.png"))),
                            "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
        
        # View control actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label("View"))
        
        # View control actions with Breeze icons
        view_actions = [
            ("zoom-in", self.on_zoom_in, "Zoom in"),
            ("zoom-out", self.on_zoom_out, "Zoom out"),
            ("zoom-fit-best", self.on_fit_view, "Fit all cards in view"),
            ("zoom-original", self.on_reset_view, "Reset to default view"),
        ]
        
        # Add view control actions to toolbar
        for icon_name, slot, tooltip in view_actions:
            action = QAction(QIcon.fromTheme(icon_name, 
                            QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / f"{icon_name}.png"))),
                            "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
        
        # Add the toolbar to the main layout
        parent_layout.addWidget(self.toolbar, 0)  # 0 means no stretch

    def create_section_label(self, text):
        """Create a section label for the toolbar"""
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 11px; margin-top: 5px; margin-bottom: 2px;")
        return label
    
    def on_draw_card(self):
        """Draw a random card and add it to the canvas with 50% chance to be reversed"""
        if not self.deck:
            print("No deck loaded!")
            return
            
        # Get a random card
        card = self.deck.get_random_card()
        if not card:
            print("Could not draw a card!")
            return
            
        # Add a 50% chance for the card to be reversed
        is_reversed = random.choice([True, False])
        
        # Add the card, possibly reversed
        self.add_specific_card(card, is_reversed=is_reversed)
            
    def add_specific_card(self, card, card_deck=None, is_reversed=False):
        """Add a specific card to the canvas, optionally reversed"""
        # Use provided deck or fall back to tab's deck
        deck_to_use = card_deck or self.deck
        
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
                
            # Create a draggable card item
            card_item = DraggableCardItem(pixmap, card, self)
            
            # Set initial rotation based on reversed status
            initial_rotation = 180 if is_reversed else 0
            card_item.setRotation(initial_rotation)
            
            # Update the animation controller's base rotation
            if hasattr(card_item, 'anim_controller'):
                card_item.anim_controller._rotation = initial_rotation
                
            # Update the card's data to reflect its reversed status
            if card_item.card_data:
                card_item.card_data['reversed'] = is_reversed
                
            # Setup wobble animation with the correct base rotation
            card_item.setup_wobble_animation(base_rotation=initial_rotation)
            
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
            
            reversed_status = "reversed" if is_reversed else "upright"
            print(f"Added card to canvas: {card['name']} ({reversed_status})")
            
            return card_item
            
        except Exception as e:
            print(f"Error adding card to canvas: {e}")
            return None
            
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
        """Flip the selected card upside down (to indicate reversed position in Tarot)"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                # First, stop all animations that might override our rotation
                if hasattr(item, 'rotation_anim'):
                    item.rotation_anim.stop()
                
                # Toggle between normal and reversed position (180° rotation)
                current_rotation = item.rotation()
                
                # If close to upright (0°), flip to reversed (180°)
                # If close to reversed (180°), flip to upright (0°)
                new_rotation = 0
                if abs(current_rotation % 360) < 90 or abs(current_rotation % 360) > 270:
                    new_rotation = 180
                
                # Set the new rotation directly
                item.setRotation(new_rotation)
                
                # Update the base rotation in the animation controller
                if hasattr(item, 'anim_controller'):
                    item.anim_controller._rotation = new_rotation
                
                # Update the card's internal state to reflect reversed status
                if hasattr(item, 'card_data') and item.card_data:
                    # Toggle the reversed flag (create if it doesn't exist)
                    item.card_data['reversed'] = new_rotation == 180
                
                # Now restart the animation with the new base rotation
                if hasattr(item, 'setup_wobble_animation'):
                    item.setup_wobble_animation(base_rotation=new_rotation)
            
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
        
    
    def on_align_cards(self):
        """Show alignment options for selected cards"""
        # This could open a small popup with alignment options:
        # - Align left, center, right
        # - Align top, middle, bottom
        # - Distribute horizontally/vertically
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
    
    def update_tab_icon(self):
        """Update the tab with a canvas icon"""
        parent = self.parent()
        if parent:
            # Find the tab widget that contains this widget
            tab_widget = None
            parent_widget = parent
            
            # Try to find a parent that has setTabIcon method (likely a QTabWidget)
            while parent_widget and not tab_widget:
                if hasattr(parent_widget, 'setTabIcon'):
                    tab_widget = parent_widget
                    break
                parent_widget = parent_widget.parent()
            
            # If we found a tab widget, update the tab icon
            if tab_widget:
                index = tab_widget.indexOf(self)
                if index >= 0:
                    # Create and set a canvas icon
                    canvas_icon = CanvasIcon()
                    tab_widget.setTabIcon(index, canvas_icon)

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