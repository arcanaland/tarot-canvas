from PyQt6.QtCore import QPointF

from tarot_canvas.ui.canvas.spread_pane import PositionModel


class SpreadSlots:
    """A canvas tab's numbered slots"""

    def init_slots(self):
        self._slots = []  # in number order
        self.positions = PositionModel(self._slots, self)

    def slots(self):
        """Every slot, in number order"""
        return tuple(self._slots)

    def lay_out_slots(self, positions, unit):
        """A slot for each position, numbered in order, where it says in card units of unit px"""
        for number, position in enumerate(positions, start=1):
            centre = QPointF(position.x * unit, position.y * unit)
            slot = self.add_slot(
                number, position.id, at=centre, label=position.label, meaning=position.meaning
            )
            slot.setPos(centre - slot.boundingRect().center())
            slot.setZValue(position.z)
            slot.set_orient(position.rotation)
            self.positions.append(slot)
        if positions:
            self._top_z = max(position.z for position in positions)
            self._bottom_z = min(position.z for position in positions)
        self.scene.clearSelection()
        self.settle_motion()

    def remove_slots(self):
        """Take every slot off the canvas, and its row out of the list"""
        self.scene.clearSelection()
        for slot in self._slots:
            self.scene.removeItem(slot)
        self.positions.remove_unplaced()
