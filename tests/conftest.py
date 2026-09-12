import atexit
import os
import shutil
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# TODO: ideally we can remove this mess when we refactor the code
# to not unconditionally read/write stuff from $HOME
_TEST_HOME = Path(tempfile.mkdtemp(prefix="tarot-canvas-tests-"))
atexit.register(shutil.rmtree, str(_TEST_HOME), ignore_errors=True)
os.environ["HOME"] = str(_TEST_HOME)
os.environ["XDG_CONFIG_HOME"] = str(_TEST_HOME / ".config")
os.environ["XDG_DATA_HOME"] = str(_TEST_HOME / ".local" / "share")

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
]


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Give each test its own QSettings file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    yield


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


@pytest.fixture
def clipboard(qapp):
    """The process-wide clipboard, emptied either side of the test."""
    from PyQt6.QtGui import QGuiApplication

    board = QGuiApplication.clipboard()
    board.clear()
    yield board
    board.clear()


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
