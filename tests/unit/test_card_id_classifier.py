import pytest

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.arcana_backend import load_deck
from tarot_canvas.models.card_id_classifier import classify_card_id
from tarot_canvas.models.deck_writer import BACK


@pytest.fixture
def whole(tmp_path, curation_file):
    return load_deck(writer.create("Whole", majors_only=False, decks_root=tmp_path / "decks"))


@pytest.fixture
def majors(tmp_path, curation_file):
    return load_deck(writer.create("Majors", majors_only=True, decks_root=tmp_path / "decks"))


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("00", "major_arcana.00"),
        ("0", "major_arcana.00"),
        ("21", "major_arcana.21"),
        ("the-fool", "major_arcana.00"),
        ("Fool", "major_arcana.00"),
        ("The High Priestess", "major_arcana.02"),
        ("high_priestess", "major_arcana.02"),
        ("ace_of_cups", "minor_arcana.cups.ace"),
        ("cups-01", "minor_arcana.cups.ace"),
        ("cups02", "minor_arcana.cups.two"),
        ("Cups 10", "minor_arcana.cups.ten"),
        ("10-cups", "minor_arcana.cups.ten"),
        ("queen-of-swords", "minor_arcana.swords.queen"),
        ("swords_queen", "minor_arcana.swords.queen"),
        ("wands-ace", "minor_arcana.wands.ace"),
        ("back", BACK),
        ("card-back", BACK),
        ("IMG_2041", None),
        ("cups", None),
        ("22", None),
        ("ace", None),
        ("two-cups-three", None),
        ("wands-11", None),
        ("", None),
    ],
)
def test_a_file_name_names_its_card(whole, stem, expected):
    assert classify_card_id(stem, whole) == expected


def test_a_minor_is_not_classified_for_a_majors_only_deck(majors):
    assert classify_card_id("ace_of_cups", majors) is None
    assert classify_card_id("02", majors) == "major_arcana.02"
