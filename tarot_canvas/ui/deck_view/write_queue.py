"""Worker queue for FS ops during deck creation"""

import contextlib
import os
from collections import deque

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from tarot_canvas.models import deck_writer


class ImagesFailed(Exception):
    """Files a batch could not place, after it placed the rest"""

    def __init__(self, files):
        super().__init__(", ".join(files))
        self.files = files


class _Reporter(QObject):
    """Lives on the GUI thread"""

    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)  # the exception, or None


class _Job(QRunnable):
    def __init__(self, call, reporter):
        super().__init__()
        self._call = call
        self._reporter = reporter

    def _progress(self, done, total):
        with contextlib.suppress(RuntimeError):
            self._reporter.progress.emit(done, total)

    def run(self):
        error = None
        try:
            self._call(self._progress)
        except Exception as caught:
            # Anything but a DeckWriteError or OSError is a bug, but must not stall the queue
            error = caught
        # RuntimeError: the queue, and so its reporter, was deleted meanwhile
        with contextlib.suppress(RuntimeError):
            self._reporter.done.emit(error)


class WriteQueue(QObject):
    progress = pyqtSignal(int, int)  # done, total
    finished = pyqtSignal()
    failed = pyqtSignal(object)  # the exception

    def __init__(self, deck_path, parent=None):
        super().__init__(parent)
        self._deck = os.fspath(deck_path)
        self._queue = deque()
        self._running = False
        self._reporter = _Reporter(self)
        self._reporter.progress.connect(self.progress)
        self._reporter.done.connect(self._on_done)

    def is_busy(self):
        return self._running or bool(self._queue)

    # -- the writer's calls -----------------------------------------------

    def place(self, card_id, image):
        self._add(lambda progress: deck_writer.place(self._deck, card_id, image, progress))

    def unplace(self, card_id):
        self._add(lambda progress: deck_writer.unplace(self._deck, card_id, progress))

    def place_unsorted(self, image):
        self._add(lambda _progress: deck_writer.place_unsorted(self._deck, image))

    def discard_unsorted(self, name):
        self._add(lambda _progress: deck_writer.discard_unsorted(self._deck, name))

    def refresh(self):
        self._add(lambda progress: deck_writer.refresh(self._deck, progress))

    def add_images(self, placements, unsorted):
        """{card_id: path} into their slots, then the rest into Unsorted, as one job"""
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

    # -- the queue --------------------------------------------------------

    def _add(self, call):
        self._queue.append(call)
        self._start_next()

    def _start_next(self):
        if self._running or not self._queue:
            return
        self._running = True
        QThreadPool.globalInstance().start(_Job(self._queue.popleft(), self._reporter))

    def _on_done(self, error):
        self._running = False
        if error is None:
            self.finished.emit()
        else:
            self.failed.emit(error)
        self._start_next()
