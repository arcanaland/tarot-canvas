import os

import pytest

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.deck_types import Card, CardImage, CardKind

IMAGES = (
    CardImage("/h2400/00.webp", "raster", 2400),
    CardImage("/h1200/00.webp", "raster", 1200),
    CardImage("/h750/00.webp", "raster", 750),
)


def fool(images):
    return Card(
        canonical_id="major_arcana.00", kind=CardKind.MAJOR, display_name="The Fool", images=images
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (1200, "/h1200/00.webp"),  # exact match
        (800, "/h1200/00.webp"),  # between two heights: the smaller that covers
        (220, "/h750/00.webp"),  # every height covers: the smallest
        (3000, "/h2400/00.webp"),  # nothing covers: the largest
    ],
)
def test_raster_for_prefers_the_smallest_covering_height(target, expected):
    assert fool(IMAGES).raster_for(target) == expected


def test_raster_for_with_no_images_is_none():
    assert fool(()).raster_for(440) is None


def test_default_image_with_no_images_is_none():
    assert fool(()).default_image() is None


@pytest.fixture
def three_height_deck(tmp_path):
    (tmp_path / "deck.toml").write_text(
        '[deck]\nschema_version = "2.0"\nname = "Three Heights"\nversion = "1.0"\n',
        encoding="utf-8",
    )
    for folder in ("h750", "h1200", "h2400"):
        (tmp_path / folder / "major_arcana").mkdir(parents=True)
        (tmp_path / folder / "minor_arcana" / "cups").mkdir(parents=True)
        (tmp_path / folder / "major_arcana" / "00.webp").write_bytes(b"")
        (tmp_path / folder / "minor_arcana" / "cups" / "ace.webp").write_bytes(b"")
        (tmp_path / folder / "minor_arcana" / "cups" / "queen.webp").write_bytes(b"")
    # Not raster folders, so never candidates.
    (tmp_path / "scalable" / "major_arcana").mkdir(parents=True)
    (tmp_path / "scalable" / "major_arcana" / "00.svg").write_bytes(b"")
    (tmp_path / "card_backs").mkdir()
    return TarotDeck(str(tmp_path))


def heights(card):
    return {image.height: image.path for image in card.images if image.height is not None}


def test_a_deck_records_every_raster_height_of_a_card(three_height_deck, tmp_path):
    by_id = {c.canonical_id: c for c in three_height_deck.get_all_cards()}
    for card_id, rel in [
        ("major_arcana.00", os.path.join("major_arcana", "00.webp")),
        ("minor_arcana.cups.ace", os.path.join("minor_arcana", "cups", "ace.webp")),
        ("minor_arcana.cups.queen", os.path.join("minor_arcana", "cups", "queen.webp")),
    ]:
        assert heights(by_id[card_id]) == {
            750: str(tmp_path / "h750" / rel),
            1200: str(tmp_path / "h1200" / rel),
            2400: str(tmp_path / "h2400" / rel),
        }


def test_the_default_image_is_h1200_over_h2400(three_height_deck, tmp_path):
    card = three_height_deck.get_card_by_id("major_arcana.00")
    assert card.default_image() == str(tmp_path / "h1200" / "major_arcana" / "00.webp")
    assert [image.height for image in card.images] == [1200, 2400, 750]


def test_a_card_with_no_raster_has_no_images(three_height_deck):
    assert three_height_deck.get_card_by_id("minor_arcana.cups.two").images == ()


def test_a_folder_prefers_png_over_webp_over_jpeg(tmp_path):
    (tmp_path / "deck.toml").write_text(
        '[deck]\nschema_version = "2.0"\nname = "Mixed"\nversion = "1.0"\n', encoding="utf-8"
    )
    folder = tmp_path / "h750" / "major_arcana"
    folder.mkdir(parents=True)
    for name in ("00.jpg", "00.webp", "00.png", "01.jpeg", "01.jpg", "02.avif"):
        (folder / name).write_bytes(b"")
    by_id = {c.canonical_id: c for c in TarotDeck(str(tmp_path)).get_all_cards()}
    assert heights(by_id["major_arcana.00"]) == {750: str(folder / "00.png")}
    assert heights(by_id["major_arcana.01"]) == {750: str(folder / "01.jpg")}
    assert heights(by_id["major_arcana.02"]) == {}
