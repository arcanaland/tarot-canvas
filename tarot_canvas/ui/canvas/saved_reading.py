"""A kept reading's tab, written to its folder a moment after anything in it changes"""

from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QDateTime, QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models import readings
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS, reading_label
from tarot_canvas.utils.logger import logger


class SavedReading(QObject):
    """Writes the tab's reading to path a moment after anything in it changes.

    The tab supplies what it holds, as reading_contents(base); the pane, its Question in
    question_edit, and its date_edit and note when it has them"""

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
        self.timer.start()

    @pyqtSlot()
    def flush(self):
        """Write now if a write is waiting"""
        if self.timer.isActive():
            self.write()
        note = getattr(self.pane, "note", None)
        if note is not None:
            note.flush()

    def reading(self):
        contents = self.tab.reading_contents(self._base)
        return replace(contents, date=self._date, question=self.question())

    @pyqtSlot()
    def write(self):
        """Write the reading, and return whether that worked"""
        self.timer.stop()
        try:
            readings.save(self.path, self.reading())
        except OSError as error:
            logger.error(f"Could not save reading {self.path}: {error}")
            return False
        reading_events().readings_changed.emit()
        return True
