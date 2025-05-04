from PyQt6.QtCore import QPointF
import math

def align_items_horizontally(items, alignment):
    """Align items horizontally"""
    if not items:
        return
    
    if alignment == "left":
        # Find leftmost edge
        leftmost = min(item.sceneBoundingRect().left() for item in items)
        # Align all to leftmost edge
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = leftmost - item_rect.left()
            item.setPos(item.pos().x() + offset, item.pos().y())
    
    elif alignment == "center":
        # Calculate average center X
        avg_center_x = sum(item.sceneBoundingRect().center().x() for item in items) / len(items)
        # Align all to average center
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = avg_center_x - item_rect.center().x()
            item.setPos(item.pos().x() + offset, item.pos().y())
    
    elif alignment == "right":
        # Find rightmost edge
        rightmost = max(item.sceneBoundingRect().right() for item in items)
        # Align all to rightmost edge
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = rightmost - item_rect.right()
            item.setPos(item.pos().x() + offset, item.pos().y())

def align_items_vertically(items, alignment):
    """Align items vertically"""
    if not items:
        return
    
    if alignment == "top":
        # Find topmost edge
        topmost = min(item.sceneBoundingRect().top() for item in items)
        # Align all to topmost edge
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = topmost - item_rect.top()
            item.setPos(item.pos().x(), item.pos().y() + offset)
    
    elif alignment == "center":
        # Calculate average center Y
        avg_center_y = sum(item.sceneBoundingRect().center().y() for item in items) / len(items)
        # Align all to average center
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = avg_center_y - item_rect.center().y()
            item.setPos(item.pos().x(), item.pos().y() + offset)
    
    elif alignment == "bottom":
        # Find bottommost edge
        bottommost = max(item.sceneBoundingRect().bottom() for item in items)
        # Align all to bottommost edge
        for item in items:
            item_rect = item.sceneBoundingRect()
            offset = bottommost - item_rect.bottom()
            item.setPos(item.pos().x(), item.pos().y() + offset)

def distribute_items_horizontally(items):
    """Distribute items horizontally with equal spacing"""
    if len(items) < 3:
        return  # Need at least 3 items to distribute
    
    # Sort items by x position
    sorted_items = sorted(items, key=lambda item: item.sceneBoundingRect().center().x())
    
    # Get leftmost and rightmost positions
    left_edge = sorted_items[0].sceneBoundingRect().center().x()
    right_edge = sorted_items[-1].sceneBoundingRect().center().x()
    
    # Calculate equal spacing
    total_width = right_edge - left_edge
    spacing = total_width / (len(sorted_items) - 1) if len(sorted_items) > 1 else 0
    
    # Reposition middle items
    for i in range(1, len(sorted_items) - 1):
        item = sorted_items[i]
        target_x = left_edge + (i * spacing)
        current_center = item.sceneBoundingRect().center()
        offset_x = target_x - current_center.x()
        item.setPos(item.pos().x() + offset_x, item.pos().y())

def distribute_items_vertically(items):
    """Distribute items vertically with equal spacing"""
    if len(items) < 3:
        return  # Need at least 3 items to distribute
    
    # Sort items by y position
    sorted_items = sorted(items, key=lambda item: item.sceneBoundingRect().center().y())
    
    # Get topmost and bottommost positions
    top_edge = sorted_items[0].sceneBoundingRect().center().y()
    bottom_edge = sorted_items[-1].sceneBoundingRect().center().y()
    
    # Calculate equal spacing
    total_height = bottom_edge - top_edge
    spacing = total_height / (len(sorted_items) - 1) if len(sorted_items) > 1 else 0
    
    # Reposition middle items
    for i in range(1, len(sorted_items) - 1):
        item = sorted_items[i]
        target_y = top_edge + (i * spacing)
        current_center = item.sceneBoundingRect().center()
        offset_y = target_y - current_center.y()
        item.setPos(item.pos().x(), item.pos().y() + offset_y)

def arrange_items_in_circle(items):
    """Arrange items in a circle while preserving their upright/reversed orientation"""
    if not items:
        return
    
    # Calculate the center point of all items
    center_x = sum(item.sceneBoundingRect().center().x() for item in items) / len(items)
    center_y = sum(item.sceneBoundingRect().center().y() for item in items) / len(items)
    center = QPointF(center_x, center_y)
    
    # Calculate a reasonable radius based on card size and item count
    # Use the first card's size as a reference
    card_width = items[0].sceneBoundingRect().width()
    card_height = items[0].sceneBoundingRect().height()
    
    # Radius should be large enough to prevent overlap
    min_dimension = min(card_width, card_height)
    radius = max(200, min_dimension * len(items) / (2 * math.pi))
    
    # Place items around the circle
    for i, item in enumerate(items):
        # Calculate angle for this item (distribute evenly around the circle)
        angle = (i / len(items)) * 2 * math.pi
        
        # Calculate new position
        new_x = center.x() + radius * math.cos(angle)
        new_y = center.y() + radius * math.sin(angle)
        
        # Center the card on this position
        item_rect = item.sceneBoundingRect()
        offset_x = new_x - item_rect.center().x()
        offset_y = new_y - item_rect.center().y()
        
        # Set the new position
        item.setPos(item.pos().x() + offset_x, item.pos().y() + offset_y)