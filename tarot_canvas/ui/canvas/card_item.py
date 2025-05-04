from PyQt6.QtWidgets import QGraphicsPixmapItem
from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup
from tarot_canvas.ui.canvas.animations import CardAnimationController
import random

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
        
    def setup_wobble_animation_with_intensity(self, base_rotation=0, rotation_amplitude=0.8, scale_amplitude=1.02):
        """Set up wobble animation with custom intensity."""
        # Stop any existing animation
        if hasattr(self, 'rotation_anim') and self.rotation_anim:
            self.rotation_anim.stop()
        
        # Create a sequential animation group for rotation
        self.rotation_anim = QSequentialAnimationGroup()

        # Create subtle rotation animations around the base rotation
        rot1 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot1.setDuration(4000 + random.randint(-500, 500))  # Randomize duration slightly
        rot1.setStartValue(base_rotation)
        rot1.setEndValue(base_rotation + rotation_amplitude)  # Configurable rotation angle
        rot1.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot2 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot2.setDuration(2000 + random.randint(-500, 500))
        rot2.setStartValue(base_rotation + rotation_amplitude)
        rot2.setEndValue(base_rotation - rotation_amplitude)  # Configurable negative rotation
        rot2.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        rot3 = QPropertyAnimation(self.anim_controller, b"rotation")
        rot3.setDuration(2000 + random.randint(-500, 500))
        rot3.setStartValue(base_rotation - rotation_amplitude)
        rot3.setEndValue(base_rotation)  # Back to neutral
        rot3.setEasingCurve(QEasingCurve.Type.InOutSine)
        
        # Add the animations to the sequence
        self.rotation_anim.addAnimation(rot1)
        self.rotation_anim.addAnimation(rot2)
        self.rotation_anim.addAnimation(rot3)
        
        # Create a very subtle scale animation with configurable scale
        self.scale_anim = QPropertyAnimation(self.anim_controller, b"scale")
        self.scale_anim.setDuration(1500 + random.randint(-300, 300))
        self.scale_anim.setStartValue(1.0)
        self.scale_anim.setEndValue(scale_amplitude)  # Configurable scale
        self.scale_anim.setLoopCount(-1)  # Loop indefinitely
        self.scale_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        
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