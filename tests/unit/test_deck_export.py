import os
import tomllib
import zipfile

import pytest
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.models import deck_export
from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_container import unpack_container
from tarot_canvas.models.deck_validation import validate_deck

FOOL = "major_arcana.00"


@pytest.fixture
def deck(tmp_path, curation_file):
    return writer.create("Test Deck", decks_root=tmp_path / "decks")


@pytest.fixture
def staging(tmp_path):
    return tmp_path / "staging"


def image(tmp_path, name):
    path = tmp_path / name
    picture = QImage(60, 100, QImage.Format.Format_RGB32)
    picture.fill(QColor("white"))
    assert picture.save(os.fspath(path))
    return path


def test_the_staged_copy_holds_no_working_files_and_validates_cleaner(deck, staging, tmp_path):
    writer.place(deck, FOOL, image(tmp_path, "fool.png"))
    writer.place_unsorted(deck, image(tmp_path, "loose.png"))

    staged = deck_export.stage(deck, staging)

    assert staged.folder.parent == staging
    assert staged.folder.name.startswith(f"{deck.name}.export.")
    assert sorted(p.name for p in staged.deck.iterdir()) == ["deck.toml", "h100"]
    assert not staged.verdict.blocks
    assert {f.code for f in validate_deck(deck).findings} - {
        f.code for f in staged.verdict.findings
    } == {"ignored-image-root-lookalike", "raster-outside-image-root"}


def test_only_the_staged_copy_lists_the_cards_left_out(deck, staging, tmp_path):
    writer.place(deck, FOOL, image(tmp_path, "fool.png"))
    working = (deck / "deck.toml").read_text(encoding="utf-8")

    staged = deck_export.stage(deck, staging, ["major_arcana.01", "major_arcana.02"])

    with open(staged.deck / "deck.toml", "rb") as handle:
        listed = tomllib.load(handle)["excluded_cards"]["cards"]
    minors = [card for card in CANONICAL_CARD_IDS if card.startswith("minor_arcana.")]
    assert listed == [*minors, "major_arcana.01", "major_arcana.02"]
    assert (deck / "deck.toml").read_text(encoding="utf-8") == working


def test_the_written_container_validates_as_the_staged_copy_did(deck, staging, tmp_path):
    writer.place(deck, FOOL, image(tmp_path, "fool.png"))
    staged = deck_export.stage(deck, staging)
    target = tmp_path / "out.tarotdeck"

    deck_export.write(staged, target)

    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    unpack_container(target, unpacked)
    assert validate_deck(unpacked) == staged.verdict
    deck_export.discard(staged)
    assert not staged.folder.exists()


def test_a_failed_copy_leaves_no_target(deck, staging, tmp_path, monkeypatch):
    staged = deck_export.stage(deck, staging)
    target = tmp_path / "out.tarotdeck"

    def fail(_source, out):
        out.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(deck_export.shutil, "copyfileobj", fail)
    with pytest.raises(OSError):
        deck_export.write(staged, target)
    assert not target.exists()


def test_a_container_holds_its_mimetype_first(deck, staging, tmp_path):
    staged = deck_export.stage(deck, staging)
    target = deck_export.write(staged, tmp_path / "out.tarotdeck")
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist()[0] == "mimetype"


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [("deck", "deck.tarotdeck"), ("deck.tarotdeck", "deck.tarotdeck"), ("deck.zip", "deck.zip")],
)
def test_a_name_without_a_suffix_gets_tarotdeck(tmp_path, chosen, expected):
    assert deck_export.with_suffix(tmp_path / chosen).name == expected


def test_the_suggested_name_is_the_slug_and_version():
    assert deck_export.suggested_name("My Tarot Deck", "1.0") == "my-tarot-deck-1.0.tarotdeck"
