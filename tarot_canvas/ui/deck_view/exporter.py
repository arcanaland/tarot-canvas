"""Export…: ask the fields, leave out empty cards, validate a staged copy, then write it"""

import logging
import os

from PyQt6.QtCore import QObject, QStandardPaths, pyqtSignal
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox

from tarot_canvas.models import deck_export
from tarot_canvas.models.deck_validation import Level
from tarot_canvas.ui.deck_view.export_dialogs import ExportFieldsDialog, FindingsDialog
from tarot_canvas.ui.library.decks.model import empty_cards
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.utils.path_helper import get_staging_directory

log = logging.getLogger(__name__)


class DeckExporter(QObject):
    running_changed = pyqtSignal(bool)
    message = pyqtSignal(str)  # for a toast

    def __init__(self, queue, current_deck, widget):
        """current_deck() is the deck as last reloaded; dialogs open over widget"""
        super().__init__(widget)
        self._queue = queue
        self._current_deck = current_deck
        self._widget = widget
        self.running = False
        self._write_failed = False
        queue.failed.connect(self._on_write_failed)

    def start(self):
        if self.running:
            return
        deck = self._current_deck()
        empty = empty_cards(deck)
        dialog = ExportFieldsDialog(deck, empty, self._widget)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        fields = dialog.changed_fields()
        dialog.deleteLater()
        if not accepted:
            return
        self._set_running(True)
        self._write_failed = False
        if fields:
            self._queue.set_fields(**fields)
        if empty:
            self._queue.exclude_cards([card.canonical_id for card in empty])
        staging = get_staging_directory()
        self._queue.then(lambda path: deck_export.stage(path, staging), self._on_staged)

    def _on_write_failed(self, _error):
        if self.running:
            self._write_failed = True

    def _on_staged(self, staged, error):
        if error is not None:
            self._fail(error)
            return
        if self._write_failed:
            # The editor has said why; what's staged isn't what was asked for
            self._finish(staged)
            return
        deck = self._current_deck()
        if staged.verdict.blocks:
            dialog = FindingsDialog(staged.verdict, deck, self._widget)
            dialog.exec()
            dialog.deleteLater()
            self._finish(staged)
            return
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        suggested = deck_export.suggested_name(deck.metadata.name, deck.metadata.version)
        path, _filter = QFileDialog.getSaveFileName(
            self._widget,
            DECK_VIEW["export_save_title"],
            os.path.join(documents, suggested),
            DECK_VIEW["export_filter"],
        )
        if not path:
            self._finish(staged)
            return
        target = deck_export.with_suffix(path)
        self._queue.in_background(
            lambda: deck_export.write(staged, target),
            lambda written, error: self._on_written(staged, written, error),
        )

    def _on_written(self, staged, written, error):
        self._finish(staged)
        if error is not None:
            self._fail(error)
            return
        warnings = [f for f in staged.verdict.findings if f.level is Level.WARNING]
        if not warnings:
            self.message.emit(DECK_VIEW["export_done"].format(file=written.name))
            return
        box = QMessageBox(self._widget)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(DECK_VIEW["export_title"])
        box.setText(DECK_VIEW["export_done_with_warnings"].format(count=len(warnings)))
        box.setDetailedText(
            "\n".join(" ".join(filter(None, (f.code, f.card, f.message))) for f in warnings)
        )
        box.exec()
        box.deleteLater()

    def _fail(self, error):
        log.warning("Could not export %s: %s", self._current_deck().root_path, error)
        self._set_running(False)
        QMessageBox.warning(
            self._widget, DECK_VIEW["export_title"], DECK_VIEW["export_failed"].format(error=error)
        )

    def _finish(self, staged):
        deck_export.discard(staged)
        self._set_running(False)

    def _set_running(self, running):
        self.running = running
        self.running_changed.emit(running)
