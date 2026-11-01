from PyQt6.QtGui import QUndoCommand

from tarot_canvas.ui.strings import CANVAS


class CardMoveCommand(QUndoCommand):
    """Undo command for card movements"""

    def __init__(self, item, old_pos, new_pos):
        super().__init__()
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos
        self.setText(
            CANVAS["move_card"].format(name=item.card_data.get("name", CANVAS["card_fallback"]))
        )

    def undo(self):
        self.item.setPos(self.old_pos)

    def redo(self):
        self.item.setPos(self.new_pos)
