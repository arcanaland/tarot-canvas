"""Filling a user-created deck"""

import logging

from PyQt6.QtCore import QEvent, QObject, QPersistentModelIndex, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox

from tarot_canvas.models import deck_writer
from tarot_canvas.models.deck_writer import DeckWriteError
from tarot_canvas.ui import units
from tarot_canvas.ui.deck_view.card_model import (
    CardRole,
    EmptySlotRole,
    KindRole,
    SlotIdRole,
    is_slot,
)
from tarot_canvas.ui.deck_view.slot_pickers import CardPicker, ImagePicker
from tarot_canvas.ui.deck_view.unsorted_strip import PathRole, UnsortedStrip
from tarot_canvas.ui.deck_view.write_queue import WriteQueue
from tarot_canvas.ui.dropped_files import dropped_files, offered_files
from tarot_canvas.ui.strings import DECK_VIEW

log = logging.getLogger(__name__)


class DeckEditor(QObject):
    """The editing capabilities for user-created decks"""

    progress = pyqtSignal(int, int)  # done, total
    written = pyqtSignal()  # a write finished or failed
    edit_state_changed = pyqtSignal()

    def __init__(self, deck, delegate, views, scroll, current_view, parent):
        """parent is the view's widget: menus, dialogs and pickers open over it

        views are the deck's item views, current_view() the one shown, and scroll the page
        they scroll in.
        """
        super().__init__(parent)
        self._widget = parent
        self._current_view = current_view
        self.delegate = delegate
        self.picker = None  # the open slot or card picker

        self.unsorted = UnsortedStrip(deck, delegate.cover_size())
        self.unsorted.files_dropped.connect(self.send_to_unsorted)
        self.unsorted.discard_requested.connect(self.discard_unsorted)
        self.unsorted.place_requested.connect(self.place_unsorted_image)
        self.unsorted.card_wanted.connect(self.choose_card)
        self.unsorted.view.selectionModel().currentChanged.connect(self.edit_state_changed)

        for view in views:
            view.setAcceptDrops(True)
            view.viewport().setAcceptDrops(True)
            view.viewport().installEventFilter(_SlotDrops(view, self))
        # Last, so it sees drags before _SlotDrops takes them
        self.drag_scroll = _DragScroll(
            scroll, [view.viewport() for view in views] + [self.unsorted]
        )

        self.queue = WriteQueue(deck.root_path, self)
        self.queue.progress.connect(self.progress)
        self.queue.finished.connect(self.written)
        self.queue.failed.connect(self._on_failed)
        # Converges whatever an interrupted write left
        self.queue.refresh()

    def is_busy(self):
        return self.queue.is_busy()

    def set_deck(self, deck):
        if not self.queue.is_busy():
            self.unsorted.settle()
        self.unsorted.set_deck(deck)

    def set_cover_size(self, cover_size):
        self.unsorted.set_cover_size(cover_size)

    # -- the view's clicks and menus ----------------------------------------

    def click(self, index):
        """click an empty slot to choose its image"""
        if index.data(EmptySlotRole) and (
            QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.choose_image(index)
            return True
        return False

    def activate(self, index):
        """Double-click or Return on an empty slot chooses its image"""
        if index.data(EmptySlotRole):
            self.choose_image(index)
            return True
        return False

    def slot_menu(self, index, card_menu):
        """Choose Image… on an empty slot; Replace… and Remove, then card_menu(index)'s, on a
        filled one"""
        if index.data(EmptySlotRole):
            menu = QMenu(self._widget)
            choose = menu.addAction(QIcon.fromTheme("list-add"), DECK_VIEW["choose_image"])
            choose.triggered.connect(lambda: self.choose_image(index))
            return menu
        slot = index.data(SlotIdRole)
        menu = card_menu(index) if index.data(CardRole) is not None else QMenu(self._widget)
        first = menu.actions()[0] if menu.actions() else None
        replace = QAction(QIcon.fromTheme("document-open"), DECK_VIEW["replace_image"], menu)
        replace.triggered.connect(lambda: self.choose_image(index))
        remove = QAction(QIcon.fromTheme("edit-delete"), DECK_VIEW["remove_card"], menu)
        remove.triggered.connect(lambda: self.queue.unplace(slot))
        menu.insertActions(first, [replace, remove])
        if first is not None:
            menu.insertSeparator(first)
        return menu

    # -- Delete -------------------------------------------------------------

    def can_delete(self):
        if self._unsorted_has_focus():
            return self.unsorted.current_name() is not None
        return bool(self._filled_selected_slots())

    def delete(self):
        """The selected cards go to Unsorted; with Unsorted focused, its image is deleted"""
        if not self.can_delete():
            return
        if self._unsorted_has_focus():
            self.discard_unsorted(self.unsorted.current_name())
            return
        for slot in self._filled_selected_slots():
            self.queue.unplace(slot)

    def _unsorted_has_focus(self):
        return self.unsorted.view.hasFocus()

    def _filled_selected_slots(self):
        return [
            index.data(SlotIdRole)
            for index in self._current_view().selectionModel().selectedIndexes()
            if is_slot(index) and not index.data(EmptySlotRole)
        ]

    # -- images into slots --------------------------------------------------

    def choose_image(self, index):
        """Unsorted's images for the slot at index, or the file chooser when there are none"""
        slot = index.data(SlotIdRole)
        if not self.unsorted.names():
            self.choose_file(slot)
            return
        strip = self.unsorted
        picker = ImagePicker(
            strip.model, PathRole, strip.view.iconSize(), strip.view.gridSize(), self._widget
        )
        picker.image_chosen.connect(lambda path: self.place_unsorted_image(path, slot))
        picker.file_requested.connect(lambda: self.choose_file(slot))
        view = self._current_view()
        rect = view.visualRect(index)
        self._show_picker(picker, view.viewport().mapToGlobal(rect.bottomLeft()))

    def choose_card(self, path, where):
        """The deck's slots, for the unsorted image at path"""
        picker = CardPicker(self.unsorted.deck, self._widget)
        picker.card_chosen.connect(lambda slot: self.place_unsorted_image(path, slot))
        self._show_picker(picker, where)

    def _show_picker(self, picker, where):
        # A popup; a click anywhere else, or Esc, closes and deletes it
        self.picker = picker
        picker.show_at(where)
        picker.setFocus(Qt.FocusReason.PopupFocusReason)

    def choose_file(self, slot):
        suffixes = " ".join(f"*{suffix}" for suffix in sorted(deck_writer.image_suffixes()))
        path, _filter = QFileDialog.getOpenFileName(
            self._widget,
            DECK_VIEW["chooser_title"],
            "",
            f"{DECK_VIEW['image_filter']} ({suffixes})",
        )
        if path:
            self.queue.place(slot, path)

    def place_unsorted_image(self, path, slot):
        self.unsorted.leave(path)
        self.queue.place(slot, path)

    def drop_on_slot(self, index, files):
        """One file fills the slot; more go to Unsorted"""
        if len(files) == 1:
            self.queue.place(index.data(SlotIdRole), files[0])
        else:
            self.send_to_unsorted(files)

    def send_to_unsorted(self, files):
        for path in self.unsorted.not_here(files):
            self.queue.place_unsorted(path)

    def discard_unsorted(self, name):
        answer = QMessageBox.question(
            self._widget,
            DECK_VIEW["delete_unsorted_title"],
            DECK_VIEW["delete_unsorted_text"].format(name=name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.queue.discard_unsorted(name)

    def _on_failed(self, error):
        log.warning("Could not change %s: %s", self.unsorted.deck.root_path, error)
        if isinstance(error, DeckWriteError):
            text = DECK_VIEW[f"write_failed.{error.reason.name.lower()}"].format(
                detail=error.detail
            )
        else:
            text = DECK_VIEW["write_failed_os"].format(error=error)
        # What did land is shown before the warning
        self.written.emit()
        QMessageBox.warning(self._widget, DECK_VIEW["write_failed_title"], text)


class _SlotDrops(QObject):
    """Local files dropped on a view of a created deck"""

    def __init__(self, view, editor):
        super().__init__(view)
        self._view = view
        self._editor = editor

    def _target(self, event):
        """(accepted, the slot's index or None)"""
        if not offered_files(event.mimeData()):
            return False, None
        index = self._view.indexAt(event.position().toPoint())
        if is_slot(index):
            return True, index
        if index.isValid() and index.data(KindRole) is not None:
            # A heading, label, note or ghost
            return False, None
        return bool(self._editor.unsorted.arriving(event.mimeData())), None

    def _highlight(self, index):
        delegate = self._editor.delegate
        target = QPersistentModelIndex(index) if index is not None else None
        if delegate.drop_target != target:
            delegate.drop_target = target
            self._view.viewport().update()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            accepted, index = self._target(event)
            self._highlight(index)
            if accepted:
                event.acceptProposedAction()
            else:
                event.ignore()
            return True
        if kind == QEvent.Type.DragLeave:
            self._highlight(None)
            return True
        if kind == QEvent.Type.Drop:
            accepted, index = self._target(event)
            self._highlight(None)
            if not accepted:
                event.ignore()
                return True
            event.acceptProposedAction()
            files = dropped_files(event.mimeData())
            if index is not None:
                self._editor.drop_on_slot(index, files)
            else:
                self._editor.send_to_unsorted(files)
            return True
        return False


class _DragScroll(QObject):
    """Scrolls the page while a file is dragged near its top or bottom edge"""

    MARGIN = 3 * units.GRID_UNIT
    MAX_STEP = units.GRID_UNIT
    INTERVAL_MS = 30

    def __init__(self, scroll, watched):
        super().__init__(scroll)
        self._scroll = scroll
        self.step = 0
        self.timer = QTimer(self)
        self.timer.setInterval(self.INTERVAL_MS)
        self.timer.timeout.connect(self._tick)
        # Each takes drops, so sees every move over it, refused or not; it decides nothing here
        for widget in watched:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            viewport = self._scroll.viewport()
            self.follow(watched.mapTo(viewport, event.position().toPoint()).y())
        elif kind in (QEvent.Type.DragLeave, QEvent.Type.Drop):
            self.follow(None)
        return False

    def follow(self, y):
        """The drag is at y in the page's viewport, or has gone (None)"""
        height = self._scroll.viewport().height()
        step = 0
        if y is not None and y < self.MARGIN:
            step = -self._speed(self.MARGIN - y)
        elif y is not None and y > height - self.MARGIN:
            step = self._speed(y - (height - self.MARGIN))
        self.step = step
        if step and not self.timer.isActive():
            self.timer.start()
        elif not step:
            self.timer.stop()

    def _speed(self, depth):
        """Faster the nearer the edge"""
        return max(1, round(self.MAX_STEP * min(depth, self.MARGIN) / self.MARGIN))

    def _tick(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.value() + self.step)
