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

# Modules that bind `deck_library` at import time via
# `from tarot_canvas.models.deck_library import deck_library`
DECK_LIBRARY_CONSUMERS = [
    "tarot_canvas.ui.command_palette",
    "tarot_canvas.ui.canvas.detail",
    "tarot_canvas.ui.tabs.canvas_tab",
    "tarot_canvas.ui.main_window",
    "tarot_canvas.ui.tabs.card_view_tab",
    "tarot_canvas.ui.tabs.deck_view_tab",
    "tarot_canvas.ui.library.tab",
    "tarot_canvas.ui.library.decks.page",
    "tarot_canvas.ui.tabs.reading_tab",
    "tarot_canvas.ui.card_explorer",
    "tarot_canvas.ui.catalog.downloads",
    "tarot_canvas.ui.library.decks.menu",
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


_startup_style = None


@pytest.fixture(autouse=True)
def startup_app_style():
    """Put back the app's style when a test changed it. On a Mac host a theme change installs
    the Mac's Fusion proxy, which has no name, and the next test's startup style was ''."""
    global _startup_style
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None and _startup_style is None:
        _startup_style = app.style().name()
    yield
    app = QApplication.instance()
    if app is not None and _startup_style and app.style().name() != _startup_style:
        app.setStyle(_startup_style)


@pytest.fixture(autouse=True)
def colour_schemes(monkeypatch):
    """Light and Dark read the bundled schemes, not the host's /usr/share."""
    from tarot_canvas.ui import colour_scheme

    monkeypatch.setattr(colour_scheme, "SCHEME_DIR", colour_scheme.BUNDLED_SCHEME_DIR)
    return colour_scheme.BUNDLED_SCHEME_DIR


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


@pytest.fixture
def spreads_base(tmp_path, monkeypatch):
    """Spreads are read from and written under a fresh directory."""
    from tarot_canvas.models import spreads

    base = tmp_path / "spreads"
    monkeypatch.setattr(spreads, "spreads_base", lambda: base)
    return base


@pytest.fixture(autouse=True)
def included_base(tmp_path, monkeypatch):
    """No spread ships unless a test puts one in this directory."""
    from tarot_canvas.models import spreads

    base = tmp_path / "included"
    monkeypatch.setattr(spreads, "included_base", lambda: base)
    return base


@pytest.fixture(autouse=True)
def backgrounds_base(tmp_path, monkeypatch):
    """Background images are copied into a fresh directory."""
    from tarot_canvas.models import backgrounds

    base = tmp_path / "backgrounds"
    monkeypatch.setattr(backgrounds, "backgrounds_base", lambda: base)
    return base


@pytest.fixture(autouse=True)
def flush_closed_widgets(monkeypatch):
    """Keep qtbot's widgets alive until it has closed them, then delete them before
    the next test runs an event loop."""
    from pytestqt.qtbot import QtBot

    kept = {}
    add_widget = QtBot.addWidget

    def add_and_keep(self, widget, *, before_close_func=None):
        key = id(widget)
        kept[key] = widget
        # A test that deletes its widget itself leaves qtbot nothing to close
        widget.destroyed.connect(lambda _=None, key=key: kept.pop(key, None))
        add_widget(self, widget, before_close_func=before_close_func)

    monkeypatch.setattr(QtBot, "addWidget", add_and_keep)
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent

    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    kept.clear()


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
def readings_base(tmp_path, monkeypatch):
    """Readings are kept under a fresh directory."""
    from tarot_canvas.models import readings

    base = tmp_path / "readings"
    monkeypatch.setattr(readings, "readings_base", lambda: base)
    return base


@pytest.fixture(autouse=True)
def fresh_reading_events(monkeypatch):
    """A ReadingEvents per test, so no test's emit reaches an earlier test's widgets."""
    monkeypatch.setattr("tarot_canvas.models.reading_events._instance", None)


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
    monkeypatch.setattr("tarot_canvas.ui.catalog.client._instance", None)
    monkeypatch.setattr("tarot_canvas.ui.catalog.client.QtTransport", _OfflineTransport)


def _no_network_download(*args, **kwargs):
    raise AssertionError("a test started a real deck download; use the fake_downloads fixture")


@pytest.fixture(autouse=True)
def fresh_deck_downloads(monkeypatch):
    """A DeckDownloads per test, whose downloads can't reach the network."""
    monkeypatch.setattr("tarot_canvas.ui.catalog.downloads._instance", None)
    monkeypatch.setattr("tarot_canvas.ui.catalog.downloads.DOWNLOAD_FACTORY", _no_network_download)


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

    monkeypatch.setattr("tarot_canvas.ui.catalog.downloads.DOWNLOAD_FACTORY", factory)
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


FULL_DECK_ART_SIZE = (60, 100)


def write_full_deck(root, name="Full Test Deck"):
    """A 78-card deck with a tiny PNG per card, laid out as the minimal fixture is."""
    from PyQt6.QtGui import QColor, QImage

    from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS

    root.mkdir(parents=True, exist_ok=True)
    (root / "deck.toml").write_text(
        f'[deck]\nname = "{name}"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    image = QImage(*FULL_DECK_ART_SIZE, QImage.Format.Format_RGB32)
    image.fill(QColor("steelblue"))
    art = root / "art.png"
    assert image.save(str(art))
    png = art.read_bytes()
    art.unlink()

    folder = root / f"h{FULL_DECK_ART_SIZE[1]}"
    for card_id in CANONICAL_CARD_IDS:
        # major_arcana.00 -> major_arcana/00.png, minor_arcana.cups.ace -> minor_arcana/cups/ace.png
        *parts, stem = card_id.split(".")
        path = folder.joinpath(*parts, f"{stem}.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
    return root


@pytest.fixture
def full_deck(tmp_path, qapp):
    from tarot_canvas.models.deck import TarotDeck

    return TarotDeck(str(write_full_deck(tmp_path / "full")))


@pytest.fixture(autouse=True)
def stub_deck_library(monkeypatch, minimal_deck):
    """Replace the import-time `deck_library` global everywhere"""
    from tarot_canvas.models.deck_library import DeckLibrary

    stub = SimpleNamespace(
        reference=lambda: minimal_deck,
        decks=lambda: [minimal_deck],
        rescan=lambda: None,
        path_key=DeckLibrary.path_key,
        _loaded={DeckLibrary.path_key(minimal_deck.root_path): minimal_deck},
    )
    # The real join and cache, run over whatever decks a test swaps in
    stub.decks_containing = partial(DeckLibrary.decks_containing, stub)
    stub.load = partial(DeckLibrary.load, stub)
    for module_path in DECK_LIBRARY_CONSUMERS:
        monkeypatch.setattr(f"{module_path}.deck_library", stub, raising=False)
    return stub


@pytest.fixture
def other_deck(tmp_path, stub_deck_library, minimal_deck):
    """A second installed deck with the same cards, to tell the copied deck apart."""
    import shutil

    from tarot_canvas.models.deck import TarotDeck

    shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "other")
    deck = TarotDeck(str(tmp_path / "other"))
    stub_deck_library.decks = lambda: [minimal_deck, deck]
    return deck
