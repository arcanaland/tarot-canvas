import pytest

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.arcana_backend import load_deck
from tarot_canvas.models.card_id_classifier import plan_images


@pytest.fixture
def whole(tmp_path, curation_file):
    return load_deck(writer.create("Whole", majors_only=False, decks_root=tmp_path / "decks"))


def test_each_recognised_file_goes_to_its_slot_and_the_rest_to_unsorted(whole):
    placements, unsorted = plan_images(
        ["/a/00.png", "/a/IMG_1.jpg", "/a/ace-of-cups.png"], whole, set()
    )

    assert placements == {
        "major_arcana.00": "/a/00.png",
        "minor_arcana.cups.ace": "/a/ace-of-cups.png",
    }
    assert unsorted == ["/a/IMG_1.jpg"]


def test_a_slot_two_files_claim_sends_both_to_unsorted(whole):
    placements, unsorted = plan_images(["/a/fool.png", "/a/01.png", "/b/00.jpg"], whole, set())

    assert placements == {"major_arcana.01": "/a/01.png"}
    assert unsorted == ["/a/fool.png", "/b/00.jpg"]


def test_a_filled_slot_is_never_replaced(whole):
    placements, unsorted = plan_images(
        ["/a/00.png", "/a/back.png"], whole, {"major_arcana.00", writer.BACK}
    )

    assert placements == {}
    assert unsorted == ["/a/00.png", "/a/back.png"]


def test_the_back_is_a_slot_like_any_other(whole):
    placements, unsorted = plan_images(["/a/card-back.png"], whole, set())

    assert placements == {writer.BACK: "/a/card-back.png"}
    assert unsorted == []
