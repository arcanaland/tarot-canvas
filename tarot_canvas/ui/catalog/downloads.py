"""Catalog deck downloads, app-wide so one outlives the library that started it"""

import enum
from functools import partial

from PyQt6.QtCore import QObject, pyqtSignal

from tarot_canvas.models.deck_install import install_dir_name
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind, PackageDownload
from tarot_canvas.utils.path_helper import get_decks_directory, get_staging_directory

# Read when a download starts, so tests can swap in one that never reaches the network
DOWNLOAD_FACTORY = PackageDownload


class DeckState(enum.Enum):
    INSTALLED = "installed"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    FAILED = "failed"


class DeckDownloads(QObject):
    changed = pyqtSignal(str)  # the entry's slug
    installed = pyqtSignal(object)  # the CatalogEntry, once its deck is on disk

    def __init__(self, download_factory=None, parent=None):
        super().__init__(parent)
        self._factory = download_factory
        self._running = {}  # slug -> (entry, download)
        self._progress = {}  # slug -> 0.0-1.0, running downloads only
        self._failures = {}  # slug -> the last DownloadFailure

    def state(self, slug):
        if slug in self._running:
            return DeckState.DOWNLOADING
        if slug in self._failures:
            return DeckState.FAILED
        return DeckState.AVAILABLE

    def progress(self, slug):
        return self._progress.get(slug)

    def failure(self, slug):
        return self._failures.get(slug)

    def start(self, entry):
        slug = entry.slug
        if slug in self._running:
            return
        self._failures.pop(slug, None)
        try:
            dest = get_decks_directory()[0] / install_dir_name(entry.identifier, slug)
        except ValueError as e:
            self._failures[slug] = DownloadFailure(FailureKind.FILESYSTEM, str(e))
            self.changed.emit(slug)
            return

        factory = self._factory or DOWNLOAD_FACTORY
        download = factory(
            entry.package_url,
            entry.package_size,
            entry.package_sha256,
            dest,
            get_staging_directory(),
            parent=self,
        )
        self._running[slug] = (entry, download)
        self._progress[slug] = 0.0
        download.progress.connect(partial(self._on_progress, slug))
        download.succeeded.connect(partial(self._on_succeeded, slug))
        download.failed.connect(partial(self._on_failed, slug))
        self.changed.emit(slug)
        download.start()

    def cancel(self, slug):
        if slug in self._running:
            self._running[slug][1].cancel()

    def _on_progress(self, slug, received, total):
        if slug not in self._running or total <= 0:
            return
        fraction = min(1.0, received / total)
        # A tile can't show less than a percent, so don't repaint for less
        if int(fraction * 100) == int(self._progress[slug] * 100):
            return
        self._progress[slug] = fraction
        self.changed.emit(slug)

    def _on_succeeded(self, slug, _path):
        entry = self._finish(slug)
        # The rescan's decks_changed turns the ghost into the installed deck
        deck_manager.rescan()
        self.installed.emit(entry)
        self.changed.emit(slug)

    def _on_failed(self, slug, failure):
        self._finish(slug)
        if failure.kind is not FailureKind.CANCELLED:
            self._failures[slug] = failure
        self.changed.emit(slug)

    def _finish(self, slug):
        entry, download = self._running.pop(slug)
        self._progress.pop(slug, None)
        download.deleteLater()
        return entry


_instance = None


def deck_downloads():
    global _instance
    if _instance is None:
        _instance = DeckDownloads()
    return _instance
