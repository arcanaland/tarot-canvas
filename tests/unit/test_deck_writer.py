import os
import re
import struct
import tomllib

import arcana_tarot
import pytest
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QColor, QImage, QImageReader

from tarot_canvas.models import deck_library as deck_library_module
from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models import library_curation
from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_library import DeckLibrary
from tarot_canvas.models.deck_writer import BACK, DeckWriteError, DeckWriteReason
from tarot_canvas.models.reference_deck import ReferenceDeck

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"
PRIESTESS = "major_arcana.02"
TWO_OF_CUPS = "minor_arcana.cups.two"


@pytest.fixture
def decks_root(tmp_path, curation_file):
    return tmp_path / "decks"


@pytest.fixture
def deck(decks_root):
    return writer.create("Test Deck", majors_only=False, decks_root=decks_root)


@pytest.fixture
def majors(decks_root):
    return writer.create("Majors", majors_only=True, decks_root=decks_root)


@pytest.fixture
def images(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    return folder


def picture(width, height):
    """A picture with detail in it, so a lossy or resampled copy differs from the original"""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    for y in range(0, height, max(1, height // 16)):
        for x in range(width):
            image.setPixelColor(x, y, QColor((x * 7) % 256, (y * 3) % 256, (x + y) % 256))
    return image


def save(folder, name, width, height, image_format=None):
    path = folder / name
    assert picture(width, height).save(os.fspath(path), image_format)
    return path


def rotated_jpeg(folder, name, width, height):
    """A JPEG stored width x height whose EXIF says to turn it 90° clockwise"""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    picture(width, height).save(buffer, "JPEG", 95)
    data = bytes(buffer.data())
    orientation = struct.pack(">HHIHH", 0x0112, 3, 1, 6, 0)
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + orientation + b"\x00" * 4
    app1 = b"Exif\x00\x00" + tiff
    segment = b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    path = folder / name
    path.write_bytes(data[:2] + segment + data[2:])
    return path


def manifest(deck):
    with open(deck / "deck.toml", "rb") as handle:
        return tomllib.load(handle)


def roots(deck):
    return sorted(entry.name for entry in deck.iterdir() if entry.is_dir() and entry.name[0] == "h")


def files(directory):
    return sorted(
        os.path.relpath(os.path.join(parent, name), directory)
        for parent, _, names in os.walk(directory)
        for name in names
    )


def height_of(path):
    reader = QImageReader(os.fspath(path))
    reader.setAutoTransform(True)
    return reader.read().height()


def pixels(image):
    return image.convertToFormat(QImage.Format.Format_RGB32)


# -- create --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("My Tarot", "my-tarot"),
        ("Tarot de l'Été", "tarot-de-l-ete"),
        ("タロット", ""),
        ("  --Æther & Ash!!  ", "ther-ash"),
        ("x" * 39 + " y", "x" * 39),
    ],
)
def test_a_slug_is_lowercase_ascii_and_hyphens(name, expected):
    assert writer.slug(name) == expected


# DECK.md §3.5's qualified-id, with no fragment
QUALIFIED_ID = re.compile(
    r"(?P<realm>[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?)+)"
    r"/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
)


def test_an_identifier_is_private_and_qualified():
    named = writer.mint_identifier("My Tarot")
    unnamed = writer.mint_identifier("タロット")

    assert re.fullmatch(r"land\.arcana\.private/deck/my-tarot-[0-9a-f]{8}", named)
    assert re.fullmatch(r"land\.arcana\.private/deck/[0-9a-f]{8}", unnamed)
    assert QUALIFIED_ID.fullmatch(named)
    assert QUALIFIED_ID.fullmatch(unnamed)


@pytest.mark.parametrize("name", ["My Tarot", "Tarot de l'Été", "タロット", "--9 Lives--"])
def test_libarcana_finds_nothing_wrong_with_a_minted_identifier(decks_root, name):
    deck = writer.create(name, majors_only=False, decks_root=decks_root)

    diagnostics = arcana_tarot.validate(arcana_tarot.load_deck(deck))

    assert [d.message for d in diagnostics if d.key == "deck.identifier"] == []


def test_a_blank_name_is_refused(decks_root):
    with pytest.raises(DeckWriteError) as raised:
        writer.create("   ", majors_only=False, decks_root=decks_root)

    assert raised.value.reason is DeckWriteReason.REQUIRED_FIELD
    assert not decks_root.exists() or not any(decks_root.iterdir())


def test_a_handmade_deck_is_a_minimal_manifest_in_a_folder_named_by_its_identifier(deck):
    table = manifest(deck)

    assert table == {
        "deck": {
            "schema_version": "2.0",
            "name": "Test Deck",
            "version": "1.0.0",
            "identifier": table["deck"]["identifier"],
        }
    }
    assert table["deck"]["identifier"].endswith("/" + deck.name)
    assert deck.name.startswith("test-deck-")
    assert sorted(os.listdir(deck)) == ["deck.toml"]


def test_a_handmade_deck_is_listed_as_handmade(deck):
    assert library_curation.is_handmade(deck)
    assert library_curation.handmade_decks() == {deck.name}


def test_a_taken_folder_name_mints_again(decks_root, monkeypatch):
    hexes = iter(["0a0a0a0a", "0a0a0a0a", "0b0b0b0b"])
    monkeypatch.setattr(writer.secrets, "token_hex", lambda _: next(hexes))

    first = writer.create("Twin", majors_only=False, decks_root=decks_root)
    second = writer.create("Twin", majors_only=False, decks_root=decks_root)

    assert first.name == "twin-0a0a0a0a"
    assert second.name == "twin-0b0b0b0b"


def test_a_full_deck_loads_with_78_cards_and_no_suit_excluded(deck):
    loaded = arcana_tarot.load_deck(deck)

    assert len(loaded.cards) == 78
    assert not any(suit.excluded for suit in loaded.suits)
    assert not any(card.images for card in loaded.cards)


def test_a_majors_only_deck_loads_with_22_cards_and_every_suit_excluded(majors):
    loaded = arcana_tarot.load_deck(majors)

    assert len(loaded.cards) == 22
    assert all(suit.excluded for suit in loaded.suits)
    assert len(manifest(majors)["excluded_cards"]["cards"]) == 56
    assert "reason" not in manifest(majors)["excluded_cards"]


def test_a_new_deck_is_majors_only_unless_told_otherwise(decks_root):
    handmade = writer.create("Default", decks_root=decks_root)

    assert len(arcana_tarot.load_deck(handmade).cards) == 22


def test_including_the_minors_makes_a_majors_only_deck_whole(majors):
    writer.include_minors(majors)

    loaded = arcana_tarot.load_deck(majors)
    assert len(loaded.cards) == 78
    assert not any(suit.excluded for suit in loaded.suits)
    assert "excluded_cards" not in manifest(majors)


def test_including_the_minors_keeps_any_other_exclusion(majors):
    path = majors / "deck.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "cards = [", 'cards = [\n    "major_arcana.21",', 1
        ),
        encoding="utf-8",
    )

    writer.include_minors(majors)

    assert manifest(majors)["excluded_cards"]["cards"] == ["major_arcana.21"]


def test_including_the_minors_in_a_whole_deck_changes_nothing(deck):
    before = (deck / "deck.toml").read_bytes()

    writer.include_minors(deck)

    assert (deck / "deck.toml").read_bytes() == before


def test_a_majors_only_deck_reports_no_exclusion_reason(majors):
    from tarot_canvas.models.arcana_backend import load_deck

    assert load_deck(majors).exclusion_reason is None


def test_a_handmade_deck_is_in_the_library_after_a_rescan(deck, decks_root, monkeypatch):
    monkeypatch.setattr(deck_library_module, "get_decks_directory", lambda: [decks_root])
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: False))
    library = DeckLibrary()

    assert [found.metadata.name for found in library.decks()] == ["Test Deck"]
    assert library.decks()[0].find_card(FOOL).images == ()


def test_reload_reads_a_placed_card_and_says_the_decks_changed(
    deck, decks_root, images, monkeypatch
):
    from tarot_canvas.models.deck_events import deck_events

    monkeypatch.setattr(deck_library_module, "get_decks_directory", lambda: [decks_root])
    monkeypatch.setattr(ReferenceDeck, "is_reference_deck_present", staticmethod(lambda: False))
    library = DeckLibrary()
    writer.place(deck, FOOL, save(images, "fool.png", 60, 100))
    changes = []
    deck_events().decks_changed.connect(lambda: changes.append(1))

    reloaded = library.reload(deck)

    assert reloaded.find_card(FOOL).default_image()
    assert library.load(deck) is reloaded
    assert library.decks() == (reloaded,)
    assert changes == [1]


def test_image_suffixes_take_rasters_and_leave_out_vectors():
    suffixes = writer.image_suffixes()

    assert ".png" in suffixes
    assert ".svg" not in suffixes


# -- set_fields ----------------------------------------------------------------------------


def test_set_fields_keeps_comments_order_and_what_it_does_not_know(deck):
    path = deck / "deck.toml"
    text = path.read_text()
    text = text.replace("[deck]\n", "# made by hand\n[deck]\n")
    text = text.replace('version = "1.0.0"\n', 'version = "1.0.0"  # bump me\nx_mood = "calm"\n')
    text += '\n[app."land.example.other"]\nkept = true\n'
    path.write_text(text)

    writer.set_fields(deck, name="Renamed", artist="A. Painter", description="Line one\nLine two")

    written = path.read_text()
    assert "# made by hand\n[deck]\n" in written
    assert 'version = "1.0.0"  # bump me\nx_mood = "calm"\n' in written
    assert '[app."land.example.other"]\nkept = true' in written
    table = manifest(deck)
    assert list(table["deck"]) == [
        "schema_version",
        "name",
        "version",
        "x_mood",
        "identifier",
        "artist",
        "description",
    ]
    assert table["deck"]["name"] == "Renamed"
    assert table["deck"]["description"] == "Line one\nLine two"
    assert table["app"] == {"land.example.other": {"kept": True}}


def test_set_fields_removes_a_blank_field_but_never_the_name(deck):
    writer.set_fields(deck, artist="Someone")
    writer.set_fields(deck, artist="", version=None)

    assert "artist" not in manifest(deck)["deck"]
    assert "version" not in manifest(deck)["deck"]
    for blank in ("", None, "  "):
        with pytest.raises(DeckWriteError) as raised:
            writer.set_fields(deck, name=blank)
        assert raised.value.reason is DeckWriteReason.REQUIRED_FIELD
    assert manifest(deck)["deck"]["name"] == "Test Deck"


def test_set_fields_refuses_the_identifier_and_schema_version(deck):
    for field in ("identifier", "schema_version", "excluded_cards"):
        with pytest.raises(TypeError):
            writer.set_fields(deck, **{field: "x"})


def test_a_deck_not_handmade_is_refused(tmp_path, images):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "deck.toml").write_text(
        '[deck]\nschema_version = "2.0"\nname = "Bought"\nidentifier = "com.example/deck/bought"\n'
    )
    image = save(images, "a.png", 10, 20)

    for call in (
        lambda: writer.set_fields(installed, name="Mine"),
        lambda: writer.place(installed, FOOL, image),
        lambda: writer.refresh(installed),
        lambda: writer.refresh(tmp_path / "nowhere"),
    ):
        with pytest.raises(DeckWriteError) as raised:
            call()
        assert raised.value.reason is DeckWriteReason.NOT_HANDMADE


# -- placing -------------------------------------------------------------------------------


def test_every_derived_image_is_h_tall_and_one_already_h_tall_is_copied(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 300, 500))
    writer.place(deck, MAGICIAN, save(images, "magician.png", 600, 1000))
    writer.place(deck, BACK, save(images, "back.jpg", 300, 520, "JPEG"))

    assert roots(deck) == ["h500"]
    assert files(deck / "h500") == [
        "card_backs/classic.jpg",
        "major_arcana/00.png",
        "major_arcana/01.png",
    ]
    for derived in files(deck / "h500"):
        assert height_of(deck / "h500" / derived) == 500
    assert (deck / "h500/major_arcana/00.png").read_bytes() == (images / "fool.png").read_bytes()
    assert (deck / "source/major_arcana/00/fool.png").read_bytes() == (
        images / "fool.png"
    ).read_bytes()


def test_the_height_is_capped_then_lowered_then_raised_from_the_originals(deck, images):
    tall = save(images, "tall.png", 2880, 4800)
    progress = []

    writer.place(deck, FOOL, tall, progress=lambda done, total: progress.append((done, total)))
    assert roots(deck) == ["h2400"]
    assert progress == [(0, 1), (1, 1)]

    writer.place(deck, BACK, save(images, "back.webp", 1200, 3000, "WEBP"))
    writer.place(deck, MAGICIAN, save(images, "short.png", 1200, 2000))
    assert roots(deck) == ["h2000"]
    assert files(deck / "h2000") == [
        "card_backs/classic.webp",
        "major_arcana/00.png",
        "major_arcana/01.png",
    ]
    fresh = QImage(os.fspath(tall)).scaledToHeight(2000, Qt.TransformationMode.SmoothTransformation)
    assert pixels(QImage(os.fspath(deck / "h2000/major_arcana/00.png"))) == pixels(fresh)

    writer.unplace(deck, MAGICIAN)
    assert roots(deck) == ["h2400"]
    assert files(deck / "h2400") == ["card_backs/classic.webp", "major_arcana/00.png"]
    for derived in files(deck / "h2400"):
        assert height_of(deck / "h2400" / derived) == 2400


def test_a_webp_source_derives_a_lossless_webp(deck, images):
    writer.place(deck, FOOL, save(images, "short.png", 100, 200))
    writer.place(deck, MAGICIAN, save(images, "tall.webp", 200, 400, "WEBP"))

    derived = deck / "h200/major_arcana/01.webp"
    assert derived.read_bytes()[12:16] == b"VP8L"


def test_a_format_outside_the_baseline_derives_a_png(deck, images):
    writer.place(deck, FOOL, save(images, "card.bmp", 120, 200, "BMP"))

    assert files(deck / "source") == ["major_arcana/00/card.bmp"]
    assert files(deck / "h200") == ["major_arcana/00.png"]


@pytest.mark.skipif(b"tiff" not in QImageReader.supportedImageFormats(), reason="no TIFF plugin")
def test_a_tiff_source_derives_a_png(deck, images):
    writer.place(deck, FOOL, save(images, "card.TIFF", 120, 200, "TIFF"))

    assert files(deck / "source") == ["major_arcana/00/card.TIFF"]
    assert files(deck / "h200") == ["major_arcana/00.png"]


def test_a_rotated_jpeg_is_re_encoded_upright(deck, images):
    sideways = rotated_jpeg(images, "phone.JPG", 400, 240)

    writer.place(deck, FOOL, sideways)

    assert roots(deck) == ["h400"]
    derived = deck / "h400/major_arcana/00.jpg"
    assert derived.read_bytes() != sideways.read_bytes()
    stored = QImageReader(os.fspath(derived))
    stored.setAutoTransform(False)
    assert stored.read().size().width() == 240
    assert (deck / "source/major_arcana/00/phone.JPG").read_bytes() == sideways.read_bytes()


def test_replacing_a_card_moves_the_old_one_to_unsorted(deck, images):
    writer.place(deck, FOOL, save(images, "first.png", 100, 200))
    writer.place(deck, FOOL, save(images, "second.jpg", 100, 200, "JPEG"))
    writer.place(deck, FOOL, save(images, "third.png", 100, 200))

    assert files(deck / "source") == ["major_arcana/00/third.png"]
    assert files(deck / "h200") == ["major_arcana/00.png"]
    assert sorted(os.listdir(deck / "unsorted")) == ["first.png", "second.jpg"]
    assert (deck / "unsorted/first.png").read_bytes() == (images / "first.png").read_bytes()


def test_unplacing_moves_the_card_to_unsorted_and_the_last_takes_the_root(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 100, 200))

    writer.unplace(deck, FOOL)

    assert roots(deck) == []
    assert files(deck / "source") == []
    assert os.listdir(deck / "unsorted") == ["fool.png"]


def test_a_card_taken_out_keeps_the_name_it_came_with_whichever_slot_it_was_in(deck, images):
    writer.place(deck, PRIESTESS, save(images, "03.png", 100, 200))
    writer.place(deck, TWO_OF_CUPS, save(images, "IMG_1.png", 100, 200))
    writer.place(deck, BACK, save(images, "IMG_2.jpg", 100, 200, "JPEG"))

    for card_id in (PRIESTESS, TWO_OF_CUPS, BACK):
        writer.unplace(deck, card_id)

    assert sorted(os.listdir(deck / "unsorted")) == ["03.png", "IMG_1.png", "IMG_2.jpg"]
    assert files(deck / "source") == []


def test_an_unsorted_image_keeps_its_name_steps_past_a_taken_one_and_moves_when_placed(
    deck, images
):
    image = save(images, "The Fool.png", 100, 200)

    assert writer.place_unsorted(deck, image) == "The Fool.png"
    assert writer.place_unsorted(deck, image) == "The Fool-2.png"
    assert writer.place_unsorted(deck, image) == "The Fool-3.png"

    writer.place(deck, FOOL, deck / "unsorted/The Fool-2.png")
    assert sorted(os.listdir(deck / "unsorted")) == ["The Fool-3.png", "The Fool.png"]

    writer.stage_unsorted(deck, "The Fool-3.png")
    writer.commit_unsorted(deck, "The Fool-3.png")
    assert os.listdir(deck / "unsorted") == ["The Fool.png"]
    with pytest.raises(ValueError):
        writer.stage_unsorted(deck, "../deck.toml")


def test_a_staged_unsorted_image_outlives_other_writes_and_comes_back_under_a_free_name(
    deck, images
):
    writer.place_unsorted(deck, save(images, "loose.png", 100, 200))
    writer.stage_unsorted(deck, "loose.png")
    writer.place_unsorted(deck, save(images, "loose.png", 100, 200))
    assert sorted(os.listdir(deck / "unsorted")) == ["loose.png", "loose.png.deleted"]

    assert writer.restore_unsorted(deck, "loose.png") == "loose-2.png"
    assert sorted(os.listdir(deck / "unsorted")) == ["loose-2.png", "loose.png"]


def test_refresh_removes_an_unsorted_image_left_staged(deck, images):
    writer.place_unsorted(deck, save(images, "loose.png", 100, 200))
    writer.stage_unsorted(deck, "loose.png")

    writer.refresh(deck)

    assert os.listdir(deck / "unsorted") == []


def test_a_minor_in_a_majors_only_deck_is_not_in_the_deck(majors, images):
    with pytest.raises(DeckWriteError) as raised:
        writer.place(majors, TWO_OF_CUPS, save(images, "two.png", 100, 200))

    assert raised.value.reason is DeckWriteReason.NOT_IN_DECK


def test_an_unknown_card_is_refused(deck, images):
    for card_id in ("major_arcana.22", "card_backs.other", "cups.two"):
        with pytest.raises(DeckWriteError) as raised:
            writer.place(deck, card_id, save(images, "x.png", 100, 200))
        assert raised.value.reason is DeckWriteReason.UNKNOWN_CARD


def test_a_file_that_is_not_an_image_is_refused(deck, images):
    text = images / "notes.png"
    text.write_text("not a picture")
    vector = images / "card.svg"
    vector.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="20"/>')

    for bad in (text, vector, images / "missing.png"):
        with pytest.raises(DeckWriteError) as raised:
            writer.place(deck, FOOL, bad)
        assert raised.value.reason is DeckWriteReason.UNREADABLE_IMAGE
        with pytest.raises(DeckWriteError):
            writer.place_unsorted(deck, bad)
    assert not (deck / "source").exists()


# -- crashes -------------------------------------------------------------------------------


def test_an_interrupted_place_still_loads_and_refresh_completes_it(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 100, 300))
    # As a crash leaves it: a half-built root for a new H, and a source with nothing derived
    partial = deck / ".h200.partial/major_arcana"
    partial.mkdir(parents=True)
    (partial / "00.png").write_bytes(b"half")
    (deck / "source/major_arcana/01").mkdir()
    (deck / "source/major_arcana/01/.magician.png.tmp").write_bytes(b"half")
    (deck / ".deck.toml.abc").write_text("half")
    save(deck / "source/major_arcana/01", "magician.png", 100, 200)

    loaded = arcana_tarot.load_deck(deck)
    assert len(loaded.cards) == 78

    writer.refresh(deck)

    assert sorted(os.listdir(deck)) == ["deck.toml", "h200", "source"]
    assert files(deck / "source") == ["major_arcana/00/fool.png", "major_arcana/01/magician.png"]
    assert files(deck / "h200") == ["major_arcana/00.png", "major_arcana/01.png"]


def test_refresh_keeps_the_newest_of_two_files_in_one_slot(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 100, 200))
    newer = save(deck / "source/major_arcana/00", "other.jpg", 100, 200, "JPEG")
    os.utime(newer, ns=(1, (deck / "source/major_arcana/00/fool.png").stat().st_mtime_ns + 10**9))

    writer.refresh(deck)

    assert files(deck / "source") == ["major_arcana/00/other.jpg"]
    assert files(deck / "h200") == ["major_arcana/00.jpg"]
    assert os.listdir(deck / "unsorted") == ["fool.png"]


def test_refresh_removes_a_derived_image_with_no_source(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 100, 200))
    save(deck / "h200/major_arcana", "05.png", 100, 200)

    writer.refresh(deck)

    assert files(deck / "h200") == ["major_arcana/00.png"]


# -- the result, through libarcana ---------------------------------------------------------


def test_placed_cards_load_with_their_images_and_validate_without_errors(deck, images):
    writer.place(deck, FOOL, save(images, "fool.png", 120, 200))
    writer.place(deck, MAGICIAN, save(images, "magician.jpg", 120, 210, "JPEG"))
    writer.place(deck, TWO_OF_CUPS, save(images, "two.webp", 120, 220, "WEBP"))
    writer.place(deck, BACK, save(images, "back.png", 120, 200))

    loaded = arcana_tarot.load_deck(deck)
    with_images = {card.canonical_id(): card.images[0].path for card in loaded.cards if card.images}
    assert with_images == {
        FOOL: deck / "h200/major_arcana/00.png",
        MAGICIAN: deck / "h200/major_arcana/01.jpg",
        TWO_OF_CUPS: deck / "h200/minor_arcana/cups/two.webp",
    }
    assert [back.id for back in loaded.card_backs] == ["classic"]

    errors = [
        diagnostic
        for diagnostic in arcana_tarot.validate(loaded)
        if diagnostic.level == arcana_tarot.severity.error
    ]
    assert errors == []
    assert set(CANONICAL_CARD_IDS) == {card.canonical_id() for card in loaded.cards}


def test_an_image_qt_will_not_decode_goes_back_to_unsorted(deck, images, monkeypatch):
    writer.place(deck, FOOL, save(images, "fool.png", 100, 200))
    huge = save(images, "huge.png", 100, 400)
    monkeypatch.setattr(QImageReader, "read", lambda self: QImage())

    with pytest.raises(DeckWriteError) as raised:
        writer.place(deck, MAGICIAN, huge)

    assert raised.value.reason is DeckWriteReason.UNREADABLE_IMAGE
    assert files(deck / "source") == ["major_arcana/00/fool.png"]
    assert os.listdir(deck / "unsorted") == ["huge.png"]
    assert files(deck / "h200") == ["major_arcana/00.png"]
    monkeypatch.undo()
    writer.refresh(deck)


# -- exclude_minors -------------------------------------------------------------------------


def test_excluding_the_minors_sends_a_placed_minors_original_to_unsorted(deck, images):
    writer.place(deck, TWO_OF_CUPS, save(images, "my-two.png", 40, 70))
    writer.place(deck, FOOL, save(images, "fool.png", 40, 70))

    writer.exclude_minors(deck)

    assert files(deck / writer.UNSORTED) == ["my-two.png"]
    assert not (deck / writer.SOURCE / "minor_arcana").exists()
    assert not any((root / "minor_arcana").exists() for root in (deck / r for r in roots(deck)))
    assert files(deck / "h70") == ["major_arcana/00.png"]
    assert sorted(manifest(deck)["excluded_cards"]["cards"]) == sorted(
        card for card in CANONICAL_CARD_IDS if card.startswith("minor_arcana.")
    )
    assert "reason" not in manifest(deck)["excluded_cards"]
    assert len(arcana_tarot.load_deck(deck).cards) == 22


def test_excluding_then_including_the_minors_round_trips(majors):
    before = manifest(majors)

    writer.include_minors(majors)
    writer.exclude_minors(majors)

    assert sorted(manifest(majors)["excluded_cards"]["cards"]) == sorted(
        before["excluded_cards"]["cards"]
    )


# -- place_many -----------------------------------------------------------------------------


def test_place_many_places_shortest_first_into_one_root(deck, images, monkeypatch):
    tall = save(images, "tall.png", 30, 4800)
    short = save(images, "short.png", 12, 2000)
    order = []
    original = writer.place

    def placing(deck_path, card_id, image, progress=None):
        order.append(card_id)
        original(deck_path, card_id, image, progress)

    monkeypatch.setattr(writer, "place", placing)
    failed = writer.place_many(deck, {FOOL: tall, MAGICIAN: short}, [])

    assert failed == []
    assert order == [MAGICIAN, FOOL]
    assert roots(deck) == ["h2000"]


def test_place_many_carries_on_past_a_failure_and_reports_it(deck, images):
    broken = images / "02.png"
    broken.write_text("not an image")
    good = save(images, "00.png", 40, 70)
    stray = save(images, "IMG_1.png", 40, 70)
    steps = []

    failed = writer.place_many(
        deck, {PRIESTESS: broken, FOOL: good}, [stray], lambda done, total: steps.append(done)
    )

    assert failed == [os.fspath(broken)]
    assert files(deck / writer.UNSORTED) == ["IMG_1.png"]
    assert files(deck / "h70") == ["major_arcana/00.png"]
    assert steps[0] == 0 and steps[-1] == 3


def test_exported_files_are_the_decks_own_and_not_its_working_files(majors, images):
    writer.place(majors, FOOL, save(images, "fool.png", 60, 100))
    writer.place_unsorted(majors, save(images, "loose.png", 60, 100))
    (majors / ".h500.partial").mkdir()
    (majors / ".h500.partial" / "x.png").write_bytes(b"x")
    (majors / ".hidden").write_text("x")
    (majors / "LICENSE.txt").write_text("CC0")
    (majors / "linked.txt").symlink_to(majors / "LICENSE.txt")

    exported = writer.exported_files(majors)

    assert [path.as_posix() for path in exported] == [
        "LICENSE.txt",
        "deck.toml",
        "h100/major_arcana/00.png",
    ]


def test_listing_excluded_cards_appends_them_once_in_canonical_order(majors, images):
    writer.place(majors, FOOL, save(images, "fool.png", 60, 100))
    path = majors / "deck.toml"

    writer.list_excluded(path, [PRIESTESS, MAGICIAN])
    writer.list_excluded(path, [MAGICIAN])

    listed = manifest(majors)["excluded_cards"]["cards"]
    assert listed[:56] == [card for card in CANONICAL_CARD_IDS if card.startswith("minor_arcana.")]
    assert listed[56:] == [MAGICIAN, PRIESTESS]
    loaded = arcana_tarot.load_deck(majors)
    assert len(loaded.cards) == 20
    assert not [
        diagnostic
        for diagnostic in arcana_tarot.validate(loaded)
        if diagnostic.level >= arcana_tarot.severity.warning
    ]
