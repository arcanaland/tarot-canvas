import hashlib
import logging

import pytest

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.esoterica import RWS, EsotericaManager
from tarot_canvas.models.esoterica_registry import Role
from tarot_canvas.utils.path_helper import BUNDLED_ESOTERICA_PATH, get_esoterica_directories

SOURCE_FILE = "mcelroy-a-guide-to-tarot-card-meanings-2014.toml"
IDENTIFIER = "land.arcana/esoterica/mcelroy-a-guide-to-tarot-card-meanings-2014"

# From the release's SHA256SUMS. A new release means updating these by hand.
PINNED_SHA256 = {
    SOURCE_FILE: "82c6bb8f5ce5ebdbcbb13719863f326b3081bd8c8e867d5e58b81c33f874ccaa",
    "PROVENANCE.toml": "4c921dddc596ef0349de2fc9c8dbd8282ebb413094cb2602794a19814b446e03",
    "LicenseRef-McElroy-Uncopyright.txt": (
        "f7f06e183c2ca43fdf4b6ad0036ed37f14cc77410a5f514e4238797cb342279e"
    ),
}


def listing():
    return sorted(p.name for p in BUNDLED_ESOTERICA_PATH.iterdir() if p.name != "__pycache__")


@pytest.fixture
def scratch(tmp_path):
    """A first root, so the bundled one is never the root that gets created"""
    return tmp_path / "primary"


@pytest.mark.parametrize("name", sorted(PINNED_SHA256))
def test_each_bundled_file_is_the_released_bytes(name):
    digest = hashlib.sha256((BUNDLED_ESOTERICA_PATH / name).read_bytes()).hexdigest()
    assert digest == PINNED_SHA256[name]


def test_the_bundle_holds_nothing_else():
    assert listing() == sorted(PINNED_SHA256)


def test_the_bundle_reads_as_one_source_for_every_card(scratch):
    manager = EsotericaManager([scratch, BUNDLED_ESOTERICA_PATH])

    assert list(manager.sources) == [IDENTIFIER]
    for card_id in CANONICAL_CARD_IDS:
        assert len(manager.read_card(card_id)) == 1, card_id


def test_some_major_has_a_labelled_symbol(scratch):
    manager = EsotericaManager([scratch, BUNDLED_ESOTERICA_PATH])

    labelled = [
        entry
        for card_id in CANONICAL_CARD_IDS
        if card_id.startswith("major_arcana.")
        for reading in manager.read_card(card_id)
        for entry in reading.entries
        if entry.role is Role.SYMBOLS and entry.label
    ]
    assert labelled


def test_the_bundle_is_written_for_the_rider_waite_smith_pattern(scratch):
    manager = EsotericaManager([scratch, BUNDLED_ESOTERICA_PATH])

    assert manager.sources[IDENTIFIER]["pattern"] == RWS


def test_loading_the_bundle_logs_no_warning(scratch, caplog):
    with caplog.at_level(logging.WARNING):
        EsotericaManager([scratch, BUNDLED_ESOTERICA_PATH])

    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_a_user_copy_with_the_same_identifier_wins(scratch):
    text = (BUNDLED_ESOTERICA_PATH / SOURCE_FILE).read_text(encoding="utf-8")
    edited = text.replace('name = "A Guide to Tarot Card Meanings"', 'name = "My Edited Copy"', 1)
    assert edited != text
    scratch.mkdir(parents=True)
    (scratch / "edited.toml").write_text(edited, encoding="utf-8")

    manager = EsotericaManager([scratch, BUNDLED_ESOTERICA_PATH])

    assert list(manager.sources) == [IDENTIFIER]
    (reading,) = manager.read_card("major_arcana.00")
    assert reading.name == "My Edited Copy"


def test_loading_the_default_roots_writes_nothing_into_the_bundle():
    before = {p.name: p.stat().st_mtime_ns for p in BUNDLED_ESOTERICA_PATH.iterdir()}

    manager = EsotericaManager()
    manager.reload()

    assert get_esoterica_directories()[0] != BUNDLED_ESOTERICA_PATH
    assert {p.name: p.stat().st_mtime_ns for p in BUNDLED_ESOTERICA_PATH.iterdir()} == before
