import os

import pytest

from tarot_canvas.models.deck import TarotDeck, pick_raster

IMAGES = {750: "/h750/00.webp", 1200: "/h1200/00.webp", 2400: "/h2400/00.webp"}


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (1200, "/h1200/00.webp"),  # exact match
        (800, "/h1200/00.webp"),  # between two heights: the smaller that covers
        (220, "/h750/00.webp"),  # every height covers: the smallest
        (3000, "/h2400/00.webp"),  # nothing covers: the largest
    ],
)
def test_pick_raster_prefers_the_smallest_covering_height(target, expected):
    assert pick_raster(IMAGES, target) == expected


def test_pick_raster_of_an_empty_map_is_none():
    assert pick_raster({}, 440) is None


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


def test_a_deck_records_every_raster_height_of_a_card(three_height_deck, tmp_path):
    by_id = {c["id"]: c for c in three_height_deck.get_all_cards()}
    for card_id, rel in [
        ("major_arcana.00", os.path.join("major_arcana", "00.webp")),
        ("minor_arcana.cups.ace", os.path.join("minor_arcana", "cups", "ace.webp")),
        ("minor_arcana.cups.queen", os.path.join("minor_arcana", "cups", "queen.webp")),
    ]:
        card = by_id[card_id]
        assert card["images"] == {
            750: str(tmp_path / "h750" / rel),
            1200: str(tmp_path / "h1200" / rel),
            2400: str(tmp_path / "h2400" / rel),
        }
        # card["image"] keeps its h1200-first order.
        assert card["image"] == str(tmp_path / "h1200" / rel)


def test_a_card_with_no_raster_has_an_empty_map(three_height_deck):
    by_id = {c["id"]: c for c in three_height_deck.get_all_cards()}
    assert by_id["minor_arcana.cups.two"]["images"] == {}


def test_a_folder_prefers_png_over_webp_over_jpeg(tmp_path):
    (tmp_path / "deck.toml").write_text(
        '[deck]\nschema_version = "2.0"\nname = "Mixed"\nversion = "1.0"\n', encoding="utf-8"
    )
    folder = tmp_path / "h750" / "major_arcana"
    folder.mkdir(parents=True)
    for name in ("00.jpg", "00.webp", "00.png", "01.jpeg", "01.jpg", "02.avif"):
        (folder / name).write_bytes(b"")
    by_id = {c["id"]: c for c in TarotDeck(str(tmp_path)).get_all_cards()}
    assert by_id["major_arcana.00"]["images"] == {750: str(folder / "00.png")}
    assert by_id["major_arcana.01"]["images"] == {750: str(folder / "01.jpg")}
    assert by_id["major_arcana.02"]["images"] == {}
