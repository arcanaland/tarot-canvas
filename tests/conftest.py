import atexit
import os
import shutil
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# TODO: ideally we can remove this mess when we refactor the code
# to not unconditionally read/write stuff from $HOME
_TEST_HOME = Path(tempfile.mkdtemp(prefix="tarot-canvas-tests-"))
atexit.register(shutil.rmtree, str(_TEST_HOME), ignore_errors=True)
os.environ["HOME"] = str(_TEST_HOME)
os.environ["XDG_CONFIG_HOME"] = str(_TEST_HOME / ".config")
os.environ["XDG_DATA_HOME"] = str(_TEST_HOME / ".local" / "share")
os.environ["XDG_CACHE_HOME"] = str(_TEST_HOME / ".cache")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINIMAL_DECK_PATH = FIXTURES_DIR / "decks" / "minimal"

# Modules that bind `deck_manager` at import time via
# `from tarot_canvas.models.deck_manager import deck_manager`
DECK_MANAGER_CONSUMERS = [
    "tarot_canvas.ui.command_palette",
    "tarot_canvas.ui.tabs.canvas_tab",
    "tarot_canvas.ui.main_window",
    "tarot_canvas.ui.tabs.card_view_tab",
    "tarot_canvas.ui.tabs.library_tab",
    "tarot_canvas.ui.components.card_explorer",
    "tarot_canvas.ui.library.deck_downloads",
]


@pytest.fixture(autouse=True)
def isolated_settings():
    """Start each test from empty QSettings.

    Qt caches the config path at the first QSettings, so every test shares one file
    under _TEST_HOME, and clearing it is what isolates them.
    """
    from tarot_canvas.settings import get_settings

    get_settings().clear()
    yield


@pytest.fixture
def notes_base(tmp_path, monkeypatch):
    """Notes are read from and written under a fresh directory."""
    from tarot_canvas.models import notes as notes_model

    base = tmp_path / "notes"
    monkeypatch.setattr(notes_model, "notes_base", lambda: base)
    return base


@pytest.fixture(autouse=True)
def block_reference_deck_network(monkeypatch):
    """No test may hit the network for the reference deck."""
    from tarot_canvas.models.reference_deck import ReferenceDeck

    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: True))
    monkeypatch.setattr(
        ReferenceDeck, "download_reference_deck", staticmethod(lambda progress_callback=None: None)
    )


@pytest.fixture(autouse=True)
def flush_closed_widgets():
    """Delete what qtbot closed before the next test runs an event loop.

    qtbot closes its widgets with deleteLater, which lands only when an event loop
    next runs, so a later test's qtbot.wait() would paint windows from tests long
    over. On Qt 6.11 a LibraryTab's delegate segfaulted doing exactly that.
    """
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent

    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def fresh_deck_events(monkeypatch):
    """A DeckEvents per test, so no test's emit reaches an earlier test's widgets."""
    monkeypatch.setattr("tarot_canvas.models.deck_events._instance", None)


class _OfflineTransport:
    """Records the catalog's requests and never answers them."""

    def __init__(self, parent=None):
        self.requests = []

    def get(self, url, *, etag=None, callback):
        self.requests.append((url, etag))


@pytest.fixture(autouse=True)
def fresh_note_events(monkeypatch):
    """A NoteEvents per test, so no test's emit reaches an earlier test's widgets."""
    monkeypatch.setattr("tarot_canvas.models.note_events._instance", None)


@pytest.fixture(autouse=True)
def fresh_deck_catalog(monkeypatch):
    """A DeckCatalog per test, so no test inherits another's session state.

    Every library a test opens activates the catalog, so its default transport is
    offline too. A test that wants replies installs a DeckCatalog of its own.
    """
    monkeypatch.setattr("tarot_canvas.ui.library.catalog_client._instance", None)
    monkeypatch.setattr("tarot_canvas.ui.library.catalog_client.QtTransport", _OfflineTransport)


def _no_network_download(*args, **kwargs):
    raise AssertionError("a test started a real deck download; use the fake_downloads fixture")


@pytest.fixture(autouse=True)
def fresh_deck_downloads(monkeypatch):
    """A DeckDownloads per test, whose downloads can't reach the network."""
    monkeypatch.setattr("tarot_canvas.ui.library.deck_downloads._instance", None)
    monkeypatch.setattr(
        "tarot_canvas.ui.library.deck_downloads.DOWNLOAD_FACTORY", _no_network_download
    )


class FakeDownload(QObject):
    """A PackageDownload that never starts; the test emits its signals."""

    progress = pyqtSignal("qint64", "qint64")
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(object)

    def __init__(self, url, size, sha256, dest, staging_root, network=None, parent=None):
        super().__init__(parent)
        self.url, self.size, self.sha256 = url, size, sha256
        self.dest, self.staging_root = Path(dest), Path(staging_root)
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        from tarot_canvas.utils.package_download import DownloadFailure, FailureKind

        self.cancelled = True
        self.failed.emit(DownloadFailure(FailureKind.CANCELLED, "cancelled"))


@pytest.fixture
def fake_downloads(monkeypatch):
    """Every download the test starts, as a FakeDownload, oldest first."""
    made = []

    def factory(*args, **kwargs):
        made.append(FakeDownload(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr("tarot_canvas.ui.library.deck_downloads.DOWNLOAD_FACTORY", factory)
    return made


@pytest.fixture
def clipboard(qapp):
    """The process-wide clipboard, emptied either side of the test."""
    from PyQt6.QtGui import QGuiApplication

    board = QGuiApplication.clipboard()
    board.clear()
    yield board
    board.clear()


# Breeze's WindowText and Window, as (text, window) RGB
THEME_COLOURS = {
    "light": ((35, 38, 41), (239, 240, 241)),
    "dark": ((252, 252, 252), (32, 35, 38)),
}


@pytest.fixture(params=sorted(THEME_COLOURS))
def theme_palette(request, qapp):
    """A light and a dark palette, for tests of colours derived from one."""
    from PyQt6.QtGui import QColor, QPalette

    text, window = THEME_COLOURS[request.param]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.WindowText, QColor(*text))
    palette.setColor(QPalette.ColorRole.Window, QColor(*window))
    return palette


@pytest.fixture
def minimal_deck():
    from tarot_canvas.models.deck import TarotDeck

    return TarotDeck(str(MINIMAL_DECK_PATH))


@pytest.fixture(autouse=True)
def stub_deck_manager(monkeypatch, minimal_deck):
    """Replace the import-time `deck_manager` global everywhere"""
    stub = SimpleNamespace(
        decks={},
        reference_deck=minimal_deck,
        get_reference_deck=lambda: minimal_deck,
        get_deck_names=lambda: [],
        get_deck=lambda name: None,
        get_all_decks=lambda: [minimal_deck],
        rescan=lambda: None,
    )
    from tarot_canvas.models.deck_manager import DeckManager

    # The real join, run over whatever get_all_decks a test swaps in
    stub.decks_containing = partial(DeckManager.decks_containing, stub)
    for module_path in DECK_MANAGER_CONSUMERS:
        monkeypatch.setattr(f"{module_path}.deck_manager", stub, raising=False)
    return stub
