from contextlib import suppress

from PyQt6.QtCore import QSignalBlocker, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import QMenu, QMessageBox, QSplitter

from tarot_canvas.models import spreads
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.models.spreads import (
    Position,
    Spread,
    next_position_id,
    offsets_from_middle,
)
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.spread_pane import SpreadPane
from tarot_canvas.ui.icons import SPREAD_ICON
from tarot_canvas.ui.strings import CANVAS, COMMANDS, READINGS, SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_slots import SpreadSlots
from tarot_canvas.utils.logger import logger


class SpreadTab(SpreadSlots, CanvasTab):
    """A canvas of numbered slots"""

    TOOLS_TITLE = SPREADS["section_slots"]
    SAVES_CANVAS = False

    def __init__(self, spread=None, path=None, parent=None):
        super().__init__(parent)
        spread = spread or Spread()
        self.spread_path = None
        self.init_slots()
        self._modified = False

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.replaceWidget(self.canvas_area, self.splitter)
        self.splitter.addWidget(self.canvas_area)
        self.pane = SpreadPane(self.positions, self.commands["canvas.summon"])
        self.pane.dock(self.splitter)

        self.pane_action = self.pane.toggle_action(self, SPREADS["pane_tooltip"])
        self.toolbar.addAction(self.pane_action)
        self.start_reading_action = QAction(
            QIcon.fromTheme("media-playback-start"), READINGS["open"], self
        )
        self.start_reading_action.triggered.connect(self.start_reading)
        self.toolbar.addAction(self.start_reading_action)
        self._build_menu()

        self._take(spread)

        self._home_timer = QTimer(self)
        self._home_timer.setSingleShot(True)
        self._home_timer.setInterval(0)
        self._home_timer.timeout.connect(self.on_home)
        self._home_on_show = bool(spread.positions)

        self.layout_changed.connect(self.mark_modified)
        self.positions.moved.connect(self.layout_changed)
        self.pane.edited.connect(self.mark_modified)
        self.pane.name_edit.textChanged.connect(self._on_name_edited)
        self.pane.slot_chosen.connect(self._select_slot)
        self.scene.selectionChanged.connect(self.show_selection)
        for changed in (self.positions.rowsInserted, self.positions.rowsRemoved):
            changed.connect(self._sync_start_reading)
        self._sync_start_reading()

        self.spread_path = path
        if path is not None:
            self.pane.set_description_open(bool(spread.description))

    def bind_commands(self):
        super().bind_commands()
        # Summoning here adds a slot, on the same key
        add_slot = self.commands["canvas.summon"]
        add_slot.setText(COMMANDS["add_slot"])
        add_slot.setIcon(QIcon.fromTheme("list-add"))

    def command_handlers(self):
        handlers = super().command_handlers()
        del handlers["canvas.flip"]
        del handlers["canvas.save_layout_as_spread"]
        return handlers

    def _menu_action(self, text, icon, slot):
        action = QAction(QIcon.fromTheme(icon), text, self)
        action.triggered.connect(slot)
        self.pane.menu.addAction(action)
        return action

    def _build_menu(self):
        self.duplicate_action = self._menu_action(
            SPREADS["duplicate"], "edit-duplicate", self.duplicate
        )
        self.revert_action = self._menu_action(SPREADS["revert"], "document-revert", self.revert)
        self.pane.menu.addSeparator()
        self.open_folder_action = self._menu_action(
            SPREADS["open_folder"], "document-open-folder", self.open_folder
        )
        self.pane.menu.aboutToShow.connect(self._sync_menu)

    def tools(self):
        return (
            ("canvas.summon", SPREADS["add_slot_tooltip"], "canvas.summon"),
            ("canvas.rotate", CANVAS["rotate_tooltip"], "canvas.rotate"),
            ("canvas.delete", CANVAS["delete_tooltip"], "window.delete"),
        )

    def showEvent(self, event):
        super().showEvent(event)
        if self._home_on_show:
            self._home_on_show = False
            self._home_timer.start()

    # -- slots -------------------------------------------------------------

    def arrange_order(self, items):
        """Slots go round an arc in number order"""
        number = {id(slot): index for index, slot in enumerate(self._slots)}
        return sorted(items, key=lambda item: number.get(id(item), len(number)))

    def add_next_slot(self, at=None):
        ids = [slot.position_id for slot in self._slots]
        slot = self.add_slot(len(self._slots) + 1, next_position_id(ids), at=at)
        self.positions.append(slot)
        self.show_selection()
        return slot

    def on_draw_card(self, at=None):
        self.add_next_slot(at)

    def add_specific_card(self, card, card_deck=None, is_reversed=False, at=None):
        """A card brought to a spread is a slot where it would have landed"""
        return self.add_next_slot(at)

    def _take(self, spread):
        """Hold spread, on a canvas with no slots"""
        self._name = spread.name
        self._sources = spread.sources
        self._extra = spread.extra
        self._position_extra = {position.id: position.extra for position in spread.positions}
        self.pane.set_document(spread.name, spread.description)
        self.lay_out_slots(spread.positions, card_unit_size().width())

    def on_delete_card(self):
        super().on_delete_card()
        self.positions.remove_unplaced()

    # -- the slot's menu ---------------------------------------------------

    def build_card_menu(self, item):
        menu = QMenu(self)
        menu.addAction(self.commands["canvas.rotate"])
        menu.addSeparator()
        menu.addAction(self.commands["canvas.delete"])
        return menu

    # -- the pane ----------------------------------------------------------

    @pyqtSlot()
    def show_selection(self):
        # A new slot is selected before it has a row
        selected = [card for card in self.selected_cards() if card in self._slots]
        self.pane.show_selected(selected[0] if len(selected) == 1 else None)

    def _select_slot(self, row):
        slot = self._slots[row]
        if self.selected_cards() != [slot]:
            # One selection change, not a clear and then a select
            with QSignalBlocker(self.scene):
                self.scene.clearSelection()
            slot.setSelected(True)

    def display_name(self):
        return self._name or SPREADS["untitled"]

    def empty_tab_icon(self):
        return QIcon.fromTheme(SPREAD_ICON)

    def tab_title(self):
        if self.has_unsaved_changes():
            return SPREADS["unsaved_tab"].format(title=self.display_name())
        return self.display_name()

    def rename_text(self):
        return self._name

    def rename_dialog_text(self):
        return SPREADS["rename_title"], SPREADS["rename_prompt"]

    def rename(self, name):
        self.pane.name_edit.setText(name)

    def _on_name_edited(self, text):
        self._name = text.strip()
        self.tab_label_changed.emit()
        self.mark_modified()

    # -- keeping it --------------------------------------------------------

    def current_spread(self):
        """What we need to serialize"""
        unit = card_unit_size().width()
        centres = [slot.pos() + slot.boundingRect().center() for slot in self._slots]
        offsets = offsets_from_middle([(c.x(), c.y()) for c in centres], unit)

        positions = tuple(
            Position(
                id=slot.position_id,
                label=slot.label,
                meaning=slot.meaning,
                x=x,
                y=y,
                rotation=slot.orient % 360,
                z=slot.zValue(),
                extra=self._position_extra.get(slot.position_id, {}),
            )
            for slot, (x, y) in zip(self._slots, offsets, strict=True)
        )

        return Spread(
            name=self._name,
            description=self.pane.description(),
            sources=self._sources,
            positions=positions,
            extra=self._extra,
        )

    def _write(self, path, spread):
        try:
            spreads.save(path, spread)
        except OSError as error:
            logger.error(f"Could not save spread to {path}: {error}")
            self._toast(SPREADS["save_failed"])
            return False
        spread_events().spreads_changed.emit()
        return True

    def can_save(self):
        return not self.arranging and (self.spread_path is None or self._modified)

    def has_unsaved_changes(self):
        return self._modified

    def save(self):
        """Write the spread to disk; one that ships with the app is saved as a new one"""
        is_new = self.spread_path is None or spreads.is_included(self.spread_path)
        path = self.spread_path
        spread = spreads.copy_of(self.current_spread(), path)
        if is_new:
            try:
                path = spreads.new_spread_dir()
            except OSError as error:
                logger.error(f"Could not create directory for a spread: {error}")
                return False
        if not self._write(path, spread):
            if is_new:
                with suppress(OSError):
                    path.rmdir()
            return False
        self.spread_path = path
        self._sources = spread.sources
        self._mark_saved()
        return True

    def _mark_saved(self):
        self._modified = False
        self.tab_label_changed.emit()

    @pyqtSlot()
    def mark_modified(self):
        if not self._modified:
            self._modified = True
            self.tab_label_changed.emit()

    # -- the pane's menu ---------------------------------------------------

    @pyqtSlot()
    def set_arranging(self, arranging):
        """The pane's list neither selects nor reorders while the arc panel is open"""
        super().set_arranging(arranging)
        self.pane.list_view.setEnabled(not arranging)
        self.duplicate_action.setEnabled(not arranging)
        window = self.window()
        if hasattr(window, "update_save_action"):
            window.update_save_action()

    def _sync_menu(self):
        self.revert_action.setEnabled(
            not self.arranging and self.spread_path is not None and self._modified
        )
        self.open_folder_action.setEnabled(
            self.spread_path is not None and not spreads.is_included(self.spread_path)
        )

    @pyqtSlot()
    def _sync_start_reading(self):
        self.start_reading_action.setEnabled(bool(self._slots))

    @pyqtSlot()
    def start_reading(self):
        """A reading of the spread as it stands, saved or not"""
        if self._slots:
            self.navigation_requested.emit("open_reading_of", self.current_spread())

    @pyqtSlot()
    def duplicate(self):
        self.navigation_requested.emit(
            "open_unsaved_spread", spreads.copy_of(self.current_spread(), self.spread_path)
        )

    @pyqtSlot()
    def revert(self):
        """Discard changes and revert the spread back to its saved file"""
        Button = QMessageBox.StandardButton
        answer = QMessageBox.warning(
            self,
            SPREADS["revert_title"],
            SPREADS["revert_text"].format(name=self.display_name()),
            Button.Discard | Button.Cancel,
            Button.Cancel,
        )
        if answer != Button.Discard:
            return
        try:
            spread = spreads.load(self.spread_path)
        except (OSError, ValueError) as error:
            logger.error(f"Could not reload spread {self.spread_path}: {error}")
            self._toast(SPREADS["open_failed"])
            return

        self.remove_slots()
        self._take(spread)
        self.layout_changed.emit()
        self._mark_saved()
        self._home_timer.start()

    @pyqtSlot()
    def open_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.spread_path))):
            logger.error(f"Could not open the folder {self.spread_path}")
            self._toast(SPREADS["open_folder_failed"])
