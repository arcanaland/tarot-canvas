"""Worker queue for FS ops during deck creation"""

import contextlib
import os
from collections import deque

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from tarot_canvas.models import deck_writer


class ImagesFailed(Exception):
    """List of files that could not be assigned"""

    def __init__(self, files):
        super().__init__(", ".join(files))
        self.files = files


class _Reporter(QObject):
    """Lives on the GUI thread"""

    progress = pyqtSignal(int, int)
    done = pyqtSignal(object, object, object)  # the exception or None, the result, the callback


class _Job(QRunnable):
    def __init__(self, call, reporter, callback=None):
        super().__init__()
        self._call = call
        self._reporter = reporter
        self._callback = callback

    def _progress(self, done, total):
        with contextlib.suppress(RuntimeError):
            self._reporter.progress.emit(done, total)

    def run(self):
        error = result = None
        try:
            result = self._call(self._progress)
        except Exception as caught:
            # Anything but a DeckWriteError or OSError is a bug, but must not stall the queue
            error = caught
        # RuntimeError: the queue, and so its reporter, was deleted meanwhile
        with contextlib.suppress(RuntimeError):
            self._reporter.done.emit(error, result, self._callback)


class WriteQueue(QObject):
    progress = pyqtSignal(int, int)  # done, total
    finished = pyqtSignal()
    failed = pyqtSignal(object)  # the exception
    busy_changed = pyqtSignal(bool)

    def __init__(self, deck_path, parent=None):
        super().__init__(parent)
        self._deck = os.fspath(deck_path)
        self._queue = deque()
        self._running = False
        self._reporter = _Reporter(self)
        self._reporter.progress.connect(self.progress)
        self._reporter.done.connect(self._on_done)
        self._outside = _Reporter(self)
        self._outside.done.connect(self._on_outside_done)

    def is_busy(self):
        return self._running or bool(self._queue)

    # -- the writer's calls -----------------------------------------------

    def place(self, card_id, image):
        self._add(lambda progress: deck_writer.place(self._deck, card_id, image, progress))

    def unplace(self, card_id):
        self._add(lambda progress: deck_writer.unplace(self._deck, card_id, progress))

    def place_unsorted(self, image):
        self._add(lambda _progress: deck_writer.place_unsorted(self._deck, image))

    def stage_unsorted(self, name):
        self._add(lambda _progress: deck_writer.stage_unsorted(self._deck, name))

    def restore_unsorted(self, name):
        self._add(lambda _progress: deck_writer.restore_unsorted(self._deck, name))

    def commit_unsorted(self, name):
        self._add(lambda _progress: deck_writer.commit_unsorted(self._deck, name))

    def refresh(self):
        self._add(lambda progress: deck_writer.refresh(self._deck, progress))

    def add_images(self, placements, unsorted):
        placements, unsorted = dict(placements), list(unsorted)

        def call(progress):
            failed = deck_writer.place_many(self._deck, placements, unsorted, progress)
            if failed:
                raise ImagesFailed(failed)

        self._add(call)

    def include_minors(self):
        self._add(lambda _progress: deck_writer.include_minors(self._deck))

    def exclude_minors(self):
        self._add(lambda progress: deck_writer.exclude_minors(self._deck, progress))

    def set_fields(self, **fields):
        self._add(lambda _progress: deck_writer.set_fields(self._deck, **fields))

    # -- calls that hand back a result ------------------------------------

    def then(self, call, callback):
        """call(deck path) once every write queued before it is done; callback(result, error)
        on this thread. No finished or failed: the deck it saw is unchanged"""
        self._add(lambda _progress: call(self._deck), callback)

    def in_background(self, call, callback):
        """call() on the pool, outside the queue; callback(result, error) on this thread"""
        QThreadPool.globalInstance().start(_Job(lambda _progress: call(), self._outside, callback))

    # -- the queue --------------------------------------------------------

    def _add(self, call, callback=None):
        was_busy = self.is_busy()
        self._queue.append((call, callback))
        self._start_next()
        if not was_busy:
            self.busy_changed.emit(True)

    def _start_next(self):
        if self._running or not self._queue:
            return
        self._running = True
        call, callback = self._queue.popleft()
        QThreadPool.globalInstance().start(_Job(call, self._reporter, callback))

    def _on_done(self, error, result, callback):
        self._running = False
        if callback is not None:
            callback(result, error)
        elif error is None:
            self.finished.emit()
        else:
            self.failed.emit(error)
        self._start_next()
        if not self.is_busy():
            self.busy_changed.emit(False)

    @staticmethod
    def _on_outside_done(error, result, callback):
        callback(result, error)
