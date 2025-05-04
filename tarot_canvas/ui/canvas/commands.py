from PyQt6.QtGui import QUndoCommand

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