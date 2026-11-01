from contextlib import suppress

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSplitter

from tarot_canvas.models import spreads
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.models.spreads import Position, Spread, next_position_id
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.spread_pane import SpreadPane
from tarot_canvas.ui.strings import CANVAS, SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.utils.logger import logger

AUTOSAVE_MS = 1000
PLACES = 3


class SpreadTab(CanvasTab):
    """A canvas of numbered slots, kept as a spread"""

    TOOLS_TITLE = SPREADS["section_slots"]

    def __init__(self, spread=None, path=None, parent=None):
        super().__init__(parent)
        spread = spread or Spread()
        self.spread_path = None
        self._slots = []  # in number order
        self._extra = spread.extra
        self._position_extra = {position.id: position.extra for position in spread.positions}

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.replaceWidget(self.canvas_area, self.splitter)
        self.splitter.addWidget(self.canvas_area)
        self.pane = SpreadPane()
        self.pane.dock(self.splitter)

        self.pane_action = QAction(self)
        self.pane_action.setToolTip(SPREADS["pane_tooltip"])
        self.pane_action.setCheckable(True)
        self.pane_action.triggered.connect(self.pane.set_open)
        self.pane.open_changed.connect(self._sync_pane_action)
        self._sync_pane_action(True)
        self.toolbar.addAction(self.pane_action)

        self.pane.set_document(spread.name, spread.usage, spread.sources)
        self._lay_out(spread.positions)
        self.refresh_slot_section()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self._write_autosave)

        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self.on_fit_view)
        self._fit_on_show = bool(spread.positions)

        self.layout_changed.connect(self.schedule_save)
        self.pane.edited.connect(self.schedule_save)
        self.pane.name_edited.connect(self.tab_label_changed)
        self.pane.label_edited.connect(self._on_label_edited)
        self.pane.meaning_edited.connect(self._on_meaning_edited)
        self.pane.slot_clicked.connect(self._select_slot)
        self.scene.selectionChanged.connect(self.refresh_slot_section)

        # Closing the window closes no tab
        QApplication.instance().aboutToQuit.connect(self.flush_pending_edits)

        if path is not None:
            self.spread_path = path
            self.commands["canvas.save"].setEnabled(False)

    def command_handlers(self):
        handlers = super().command_handlers()
        del handlers["canvas.summon"], handlers["canvas.flip"]
        return {
            "canvas.add_slot": self.add_next_slot,
            "canvas.save": self.on_save,
            **handlers,
        }

    def tools(self):
        return (
            ("canvas.add_slot", SPREADS["add_slot_tooltip"], "canvas.add_slot"),
            ("canvas.rotate", CANVAS["rotate_tooltip"], "canvas.rotate"),
            ("canvas.delete", CANVAS["delete_tooltip"], "window.delete"),
            ("canvas.save", SPREADS["save_tooltip"], "canvas.save"),
        )

    def showEvent(self, event):
        super().showEvent(event)
        if self._fit_on_show:
            self._fit_on_show = False
            self._fit_timer.start()

    # -- slots -------------------------------------------------------------

    def slots(self):
        """Every slot, in number order"""
        return tuple(self._slots)

    def add_next_slot(self, at=None):
        ids = [slot.position_id for slot in self._slots]
        slot = self.add_slot(len(self._slots) + 1, next_position_id(ids), at=at)
        self._slots.append(slot)
        self.refresh_slot_section()
        return slot

    def on_draw_card(self, at=None):
        self.add_next_slot(at)

    def add_specific_card(self, card, card_deck=None, is_reversed=False, at=None):
        """A card brought to a spread is a slot where it would have landed"""
        return self.add_next_slot(at)

    def _lay_out(self, positions):
        unit = card_unit_size().width()
        for number, position in enumerate(positions, start=1):
            centre = QPointF(position.x * unit, position.y * unit)
            slot = self.add_slot(
                number, position.id, at=centre, label=position.label, meaning=position.meaning
            )
            slot.setPos(centre - slot.boundingRect().center())
            slot.setZValue(position.z)
            slot.set_orient(position.rotation)
            self._slots.append(slot)
        if positions:
            self._top_z = max(position.z for position in positions)
            self._bottom_z = min(position.z for position in positions)
        self.scene.clearSelection()
        self.settle_motion()

    def on_delete_card(self):
        super().on_delete_card()
        self._slots = [slot for slot in self._slots if slot.scene() is not None]
        self._renumber()

    def move_slot(self, slot, index):
        """Give slot the place index in the numbering"""
        self._slots.remove(slot)
        self._slots.insert(index, slot)
        self._renumber()
        self.layout_changed.emit()

    def _renumber(self):
        for number, slot in enumerate(self._slots, start=1):
            if slot.number != number:
                slot.set_number(number)
        self.refresh_slot_section()

    # -- the slot's menu ---------------------------------------------------

    def build_card_menu(self, item):
        single = len(self.selected_cards()) == 1
        index = self._slots.index(item)

        menu = QMenu(self)
        edit_label = menu.addAction(QIcon.fromTheme("edit-rename"), SPREADS["edit_label"])
        edit_label.triggered.connect(self.edit_label)
        edit_label.setEnabled(single)
        edit_meaning = menu.addAction(QIcon.fromTheme("document-edit"), SPREADS["edit_meaning"])
        edit_meaning.triggered.connect(self.edit_meaning)
        edit_meaning.setEnabled(single)

        number_menu = menu.addMenu(SPREADS["number"])
        number_menu.setEnabled(single)
        for text, icon, target, allowed in (
            (SPREADS["move_earlier"], "go-up", index - 1, index > 0),
            (SPREADS["move_later"], "go-down", index + 1, index < len(self._slots) - 1),
            (SPREADS["make_first"], "go-top", 0, index > 0),
        ):
            action = number_menu.addAction(QIcon.fromTheme(icon), text)
            action.setEnabled(allowed)
            action.triggered.connect(
                lambda _checked=False, target=target: self.move_slot(item, target)
            )

        menu.addSeparator()
        menu.addAction(self.commands["canvas.rotate"])
        menu.addSeparator()
        menu.addAction(self.commands["canvas.delete"])
        return menu

    def edit_label(self):
        self.pane.set_open(True)
        self.pane.focus_label()

    def edit_meaning(self):
        self.pane.set_open(True)
        self.pane.focus_meaning()

    # -- the pane ----------------------------------------------------------

    @pyqtSlot()
    def refresh_slot_section(self):
        selected = self.selected_cards()
        if len(selected) == 1:
            slot = selected[0]
            self.pane.show_slot(slot.number, slot.label, slot.meaning)
        else:
            self.pane.show_slots([(slot.number, slot.label) for slot in self._slots])

    def _sync_pane_action(self, is_open):
        self.pane_action.setChecked(is_open)
        name = "sidebar-collapse-right" if is_open else "sidebar-expand-right"
        self.pane_action.setIcon(QIcon.fromTheme(name))

    def _on_label_edited(self, text):
        (slot,) = self.selected_cards()
        slot.set_label(text)
        self.schedule_save()

    def _on_meaning_edited(self, text):
        (slot,) = self.selected_cards()
        slot.meaning = text
        self.schedule_save()

    def _select_slot(self, row):
        self.scene.clearSelection()
        self._slots[row].setSelected(True)

    def tab_title(self):
        return self.pane.name() or SPREADS["untitled"]

    def rename_text(self):
        return self.pane.name()

    def rename(self, name):
        self.pane.set_name(name)

    # -- keeping it --------------------------------------------------------

    def current_spread(self):
        """What the file should hold: x and y in card widths from the layout's centre"""
        unit = card_unit_size().width()
        centres = [slot.pos() + slot.boundingRect().center() for slot in self._slots]
        middle = QPointF()
        if centres:
            xs, ys = [c.x() for c in centres], [c.y() for c in centres]
            middle = QPointF((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

        positions = tuple(
            Position(
                id=slot.position_id,
                label=slot.label,
                meaning=slot.meaning,
                x=round((centre.x() - middle.x()) / unit, PLACES),
                y=round((centre.y() - middle.y()) / unit, PLACES),
                rotation=slot.orient % 360,
                z=slot.zValue(),
                extra=self._position_extra.get(slot.position_id, {}),
            )
            for slot, centre in zip(self._slots, centres, strict=True)
        )
        return Spread(
            name=self.pane.name(),
            usage=self.pane.usage(),
            sources=self.pane.sources(),
            positions=positions,
            extra=self._extra,
        )

    def _write(self, path):
        try:
            spreads.save(path, self.current_spread())
        except OSError as error:
            logger.error(f"Could not save spread to {path}: {error}")
            toast = getattr(self.window(), "toast", None)
            if toast is not None:
                toast.show_message(SPREADS["save_failed"])
            return False
        spread_events().spreads_changed.emit()
        return True

    def on_save(self):
        """The first save makes the folder. Autosave keeps it after that"""
        if self.spread_path is not None:
            return
        try:
            path = spreads.new_spread_dir()
        except OSError as error:
            logger.error(f"Could not make a folder for a spread: {error}")
            return
        if not self._write(path):
            with suppress(OSError):
                path.rmdir()
            return
        self.spread_path = path
        self.commands["canvas.save"].setEnabled(False)

    @pyqtSlot()
    def schedule_save(self):
        if self.spread_path is not None:
            self.autosave_timer.start()

    @pyqtSlot()
    def _write_autosave(self):
        self._write(self.spread_path)

    @pyqtSlot()
    def flush_pending_edits(self):
        if self.autosave_timer.isActive():
            self.autosave_timer.stop()
            self._write(self.spread_path)

    def about_to_close(self):
        self.flush_pending_edits()
