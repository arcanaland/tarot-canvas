import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

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
    """Set fake home"""
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
    )
    for module_path in DECK_MANAGER_CONSUMERS:
        monkeypatch.setattr(f"{module_path}.deck_manager", stub, raising=False)
    return stub
