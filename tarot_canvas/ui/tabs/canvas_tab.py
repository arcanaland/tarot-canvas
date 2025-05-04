from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsView, QToolBar, QVBoxLayout, QWidget, 
                           QPushButton, QHBoxLayout, QFrame, QSizePolicy, 
                           QApplication, QLabel, QMenu)
from PyQt6.QtCore import (Qt, QRectF, pyqtSignal, QPointF, QTimer, QSize, 
                         QSettings)
from PyQt6.QtGui import (QIcon, QAction, QPixmap, QBrush, QColor, QPainter, 
                       QUndoStack, QRadialGradient, QKeySequence, QCursor)

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab

# Import the refactored components
from tarot_canvas.ui.canvas import (
    DraggableCardItem, PannableGraphicsView, CanvasIcon,
    align_items_horizontally, align_items_vertically,
    distribute_items_horizontally, distribute_items_vertically,
    arrange_items_in_circle
)

import os
import random
from pathlib import Path

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
        
        # Apply background from settings
        self.apply_background_settings()
        
        # Set sensible sizing policies for the view
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view.setMinimumSize(400, 300)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add canvas to layout (will take most of the space)
        main_layout.addWidget(self.view, 1)
        
        # Create toolbar on the right
        self.create_toolbar(main_layout)
        
        # Set up the base layout
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
    
    def apply_background_settings(self):
        """Apply background settings from preferences"""
        settings = QSettings("ArcanaLand", "TarotCanvas")
        
        # Get the background style preference
        bg_style = settings.value("appearance/background_style", "Gradient")
        
        if bg_style == "Checkerboard":
            self.create_purple_checkerboard_background()
        elif bg_style == "Gradient":
            self.create_gradient_background()
        elif bg_style == "Solid Color":
            bg_color = settings.value("appearance/background_color", "#1E1432")
            self.create_solid_color_background(bg_color)
        
        # Apply animation settings
        enable_animations = settings.value("appearance/enable_animations", True, type=bool)
        animation_intensity = settings.value("appearance/animation_intensity", 50, type=int)
        
        # Update all card animations
        self.update_card_animations(enable_animations, animation_intensity)

    def create_gradient_background(self):
        """Create a gradient background for the canvas"""
        center = QPointF(0, 0)
        radius = 800
        gradient = QRadialGradient(center, radius)
        
        gradient.setColorAt(0, QColor(50, 30, 80))   # Center - medium purple
        gradient.setColorAt(0.5, QColor(30, 18, 60)) # Middle - darker purple
        gradient.setColorAt(1, QColor(15, 10, 30))   # Edge - very dark purple
        
        brush = QBrush(gradient)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)

    def create_solid_color_background(self, color_str):
        """Create a solid color background for the canvas"""
        color = QColor(color_str)
        brush = QBrush(color)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)

    def create_purple_checkerboard_background(self):
        """Create a purple checkerboard pattern background for the canvas"""
        light_purple = QColor(220, 210, 240)  # Light lavender
        dark_purple = QColor(180, 160, 220)   # Darker lavender
        
        size = 50  # Size of each square
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)
        
        painter.setBrush(QBrush(light_purple))
        painter.drawRect(0, 0, size, size)
        painter.drawRect(size, size, size, size)
        
        painter.setBrush(QBrush(dark_purple))
        painter.drawRect(0, size, size, size)
        painter.drawRect(size, 0, size, size)
        
        painter.end()
        
        pattern_brush = QBrush(pixmap)
        self.view.setBackgroundBrush(pattern_brush)

    def update_card_animations(self, enable, intensity):
        """Update all card animations based on settings"""
        # Scale intensity from 0-100 to appropriate animation values
        rotation_amplitude = intensity * 0.016  # 0 to 1.6 degrees
        scale_amplitude = 1.0 + (intensity * 0.0004)  # 1.0 to 1.04
        
        # Get all card items in the scene
        for item in self.scene.items():
            if isinstance(item, DraggableCardItem):
                # Update animation settings
                if hasattr(item, 'rotation_anim'):
                    # Stop any existing animation
                    item.rotation_anim.stop()
                    
                    if enable:
                        # Get current rotation/state
                        base_rotation = item.rotation()
                        if hasattr(item, 'anim_controller'):
                            item.anim_controller._rotation = base_rotation
                        
                        # Set up animation with new intensity
                        item.setup_wobble_animation_with_intensity(
                            base_rotation, 
                            rotation_amplitude, 
                            scale_amplitude
                        )
                        
                        # Start the animation
                        item.start_animations()
    
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
        """Draw a random card from the selected deck in Card Explorer (or default deck)"""
        # Get the main window to access the card explorer
        main_window = self.window()
        if not main_window:
            print("Couldn't find main window")
            return
        
        # Try to find the card explorer in the main window
        selected_deck = None
        try:
            # Find card explorer in the main window
            card_explorer = None
            for child in main_window.findChildren(QWidget):
                if hasattr(child, 'current_deck') and hasattr(child, 'deck_selector'):
                    card_explorer = child
                    break
            
            # Get the currently selected deck from the explorer if it exists
            if card_explorer and card_explorer.current_deck:
                selected_deck = card_explorer.current_deck
        except Exception as e:
            print(f"Error accessing card explorer: {e}")
        
        # Use the selected deck or fall back to the default deck
        deck_to_use = selected_deck or self.deck
        if not deck_to_use:
            print("No deck available to draw from!")
            return
        
        # Get a random card from the selected deck
        card = deck_to_use.get_random_card()
        if not card:
            print(f"Could not draw a card from {deck_to_use.get_name()}!")
            return
        
        # Add a 50% chance for the card to be reversed
        is_reversed = random.choice([True, False])
        
        # Add the card, possibly reversed, using the selected deck
        self.add_specific_card(card, card_deck=deck_to_use, is_reversed=is_reversed)
        
        # Log what deck we drew from
        print(f"Drew card from {deck_to_use.get_name()} deck")
            
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
        items = self.scene.selectedItems()
        # Only proceed if we have 2+ cards selected
        if len(items) < 2:
            return
        
        # Create a popup menu with alignment options
        menu = QMenu(self)
        
        # Horizontal alignment actions
        horizontal_menu = menu.addMenu("Horizontal Align")
        horizontal_menu.setIcon(QIcon.fromTheme("align-horizontal-left", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-horizontal-left.png"))))
        
        h_left = horizontal_menu.addAction("Left Edges")
        h_left.setIcon(QIcon.fromTheme("align-horizontal-left", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-horizontal-left.png"))))
        
        h_center = horizontal_menu.addAction("Centers")
        h_center.setIcon(QIcon.fromTheme("align-horizontal-center", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-horizontal-center.png"))))
        
        h_right = horizontal_menu.addAction("Right Edges")
        h_right.setIcon(QIcon.fromTheme("align-horizontal-right", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-horizontal-right.png"))))
        
        # Vertical alignment actions
        vertical_menu = menu.addMenu("Vertical Align")
        vertical_menu.setIcon(QIcon.fromTheme("align-vertical-top", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-vertical-top.png"))))
        
        v_top = vertical_menu.addAction("Top Edges")
        v_top.setIcon(QIcon.fromTheme("align-vertical-top", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-vertical-top.png"))))
        
        v_center = vertical_menu.addAction("Centers")
        v_center.setIcon(QIcon.fromTheme("align-vertical-center", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-vertical-center.png"))))
        
        v_bottom = vertical_menu.addAction("Bottom Edges")
        v_bottom.setIcon(QIcon.fromTheme("align-vertical-bottom", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "align-vertical-bottom.png"))))
        
        # Distribution options
        menu.addSeparator()
        
        distribute_h = menu.addAction("Distribute Horizontally")
        distribute_h.setIcon(QIcon.fromTheme("distribute-horizontal-center", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "distribute-horizontal-center.png"))))
        
        distribute_v = menu.addAction("Distribute Vertically")
        distribute_v.setIcon(QIcon.fromTheme("distribute-vertical-center", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "distribute-vertical-center.png"))))
        
        # Circle arrangement (useful for tarot spread)
        menu.addSeparator()
        circle_arrange = menu.addAction("Arrange in Circle")
        circle_arrange.setIcon(QIcon.fromTheme("object-rotate-right", 
                        QIcon(str(Path(__file__).parent.parent.parent / "resources" / "icons" / "object-rotate-right.png"))))
        
        # Connect actions to alignment functions
        h_left.triggered.connect(lambda: align_items_horizontally(items, "left"))
        h_center.triggered.connect(lambda: align_items_horizontally(items, "center"))
        h_right.triggered.connect(lambda: align_items_horizontally(items, "right"))
        
        v_top.triggered.connect(lambda: align_items_vertically(items, "top"))
        v_center.triggered.connect(lambda: align_items_vertically(items, "center"))
        v_bottom.triggered.connect(lambda: align_items_vertically(items, "bottom"))
        
        distribute_h.triggered.connect(lambda: distribute_items_horizontally(items))
        distribute_v.triggered.connect(lambda: distribute_items_vertically(items))
        
        circle_arrange.triggered.connect(lambda: arrange_items_in_circle(items))
        
        # Show the menu at the cursor position
        menu.exec(QCursor.pos())
    
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