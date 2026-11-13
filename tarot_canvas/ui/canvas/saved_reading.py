"""Tab for a saved reading"""

import logging
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QDateTime, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models import readings
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS, reading_label

log = logging.getLogger(__name__)


class SavedReading(QObject):
    """Writes the tab's reading to path a moment after anything in it changes."""

    # The Question or the Date changed, so the tab's label may have
    label_changed = pyqtSignal()

    def __init__(self, tab, path, reading, pane):
        super().__init__(tab)
        self.tab = tab
        self.path = Path(path)
        # Carries what the tab does not hold
        self._base = reading
        self._date = reading.date
        self.pane = pane
        # Set once the tab has closed: nothing it does after is written
        self._closed = False

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(AUTOSAVE_MS)
        self.timer.timeout.connect(self.write)

        tab.layout_changed.connect(self.schedule)
        pane.question_edit.textChanged.connect(self.schedule)
        pane.question_edit.textChanged.connect(self.label_changed)
        date_edit = getattr(pane, "date_edit", None)
        if date_edit is not None:
            date_edit.dateTimeChanged.connect(self._on_date_edited)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.flush)

    def question(self):
        return self.pane.question_edit.text().strip()

    def date(self):
        return self._date

    def label(self):
        return reading_label(self.question(), self._date)

    def set_question(self, text):
        self.pane.question_edit.setText(text)

    @pyqtSlot(QDateTime)
    def _on_date_edited(self, edited):
        self._date = edited.toPyDateTime().astimezone()
        self.schedule()
        self.label_changed.emit()

    @pyqtSlot()
    def schedule(self):
        if not self._closed:
            self.timer.start()

    @pyqtSlot()
    def flush(self):
        """Write now if a write is waiting"""
        if self.timer.isActive():
            self.write()
        note = getattr(self.pane, "note", None)
        if note is not None:
            note.flush()

    def close(self):
        """Write what is waiting, and nothing after: the closed tab lives on, unseen"""
        self.flush()
        self._closed = True
        self.timer.stop()
        note = getattr(self.pane, "note", None)
        if note is not None:
            note.timer.stop()

    def reading(self):
        contents = self.tab.reading_contents(self._base)
        return replace(contents, date=self._date, question=self.question())

    @pyqtSlot()
    def write(self):
        """Write the reading, and return whether that worked"""
        self.timer.stop()
        # Deleted from the Library, the folder stays gone
        if not self.path.is_dir():
            log.warning("Did not save reading %s: its folder is gone", self.path)
            return False
        try:
            readings.save(self.path, self.reading())
        except OSError as error:
            log.exception("Could not save reading %s: %s", self.path, error)
            return False
        reading_events().readings_changed.emit()
        return True
