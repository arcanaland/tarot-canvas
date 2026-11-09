import tomllib
from datetime import datetime, timedelta, timezone

import pytest

from tarot_canvas.models import readings, toml_files
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.models.readings import Reading, ReadingCard
from tarot_canvas.models.spreads import Position, Spread

PACIFIC = timezone(timedelta(hours=-8))
WHEN = datetime(2026, 11, 9, 21, 14, tzinfo=PACIFIC)


def sample(**changes):
    fields = {
        "date": WHEN,
        "question": 'Will the "move" go well? \\ #1 — ¿sí?',
        "deck": "rider-waite-smith",
        "reversals": True,
        "cards": (
            ReadingCard("minor_arcana.cups.king", deck="rider-waite-smith", x=-180.0, z=1.0),
            ReadingCard("major_arcana.16", reversed=True, deck="marseille", x=40.0, z=2.0),
        ),
    }
    fields.update(changes)
    return Reading(**fields)


def snapshot():
    return Spread(
        name="Cross",
        description="Two cards.\nOne crosses.",
        sources=({"url": "https://example.org/cross"},),
        positions=(
            Position("p1", "Present", "Now", 0.0, 0.0, 0.0, 1.0),
            Position("p2", "Crossing", "", 0.0, 0.0, 90.0, 2.0, {"x_colour": "red"}),
        ),
    )


def table_of(folder):
    return tomllib.loads((folder / "reading.toml").read_text())


def write(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "reading.toml").write_text(text)
    return folder


def test_a_reading_survives_a_round_trip(tmp_path):
    readings.save(tmp_path, sample())
    assert readings.load(tmp_path) == sample()


def test_the_question_is_kept_on_one_line(tmp_path):
    readings.save(tmp_path, sample(question="Two\nlines\r\nhere "))
    assert readings.load(tmp_path).question == "Two lines here"


def test_no_question_writes_no_key_and_loads_empty(tmp_path):
    readings.save(tmp_path, sample(question=""))
    assert "question" not in table_of(tmp_path)
    assert readings.load(tmp_path).question == ""


def test_a_reversed_card_at_ninety_degrees_keeps_both(tmp_path):
    card = ReadingCard("major_arcana.0", reversed=True, deck="rider-waite-smith", rotation=90.0)
    readings.save(tmp_path, sample(cards=(card,)))
    assert readings.load(tmp_path).cards == (card,)


def test_a_card_from_the_default_deck_names_none_and_another_deck_names_its_own(tmp_path):
    readings.save(tmp_path, sample())
    first, second = table_of(tmp_path)["cards"]
    assert "deck" not in first
    assert second["deck"] == "marseille"
    assert [card.deck for card in readings.load(tmp_path).cards] == [
        "rider-waite-smith",
        "marseille",
    ]


def test_the_same_card_twice_from_two_decks(tmp_path):
    cards = (
        ReadingCard("major_arcana.1", deck="rider-waite-smith"),
        ReadingCard("major_arcana.1", deck="marseille", z=1.0),
    )
    readings.save(tmp_path, sample(cards=cards))
    assert readings.load(tmp_path).cards == cards


@pytest.mark.parametrize("reversals", [None, False, True])
def test_reversals_are_absent_false_or_true(tmp_path, reversals):
    readings.save(tmp_path, sample(reversals=reversals))
    assert table_of(tmp_path).get("reversals") == reversals
    assert readings.load(tmp_path).reversals is reversals


def test_a_spread_snapshot_round_trips_without_an_app_table(tmp_path):
    reading = sample(spread=snapshot(), spread_from="1792512000")
    readings.save(tmp_path, reading)

    table = table_of(tmp_path)["spread"]
    assert table["from"] == "1792512000"
    assert "app" not in table
    assert readings.load(tmp_path) == reading


def test_a_reading_with_no_spread_has_no_spread_table(tmp_path):
    readings.save(tmp_path, sample())
    assert "spread" not in table_of(tmp_path)
    assert readings.load(tmp_path).spread is None


def test_a_bad_spread_is_dropped_and_the_reading_still_loads(tmp_path):
    write(
        tmp_path,
        "date = 2026-11-09T21:14:00-08:00\n"
        "[spread]\nname = 'Cross'\npositions = 'not an array'\n"
        "[[cards]]\nid = 'major_arcana.0'\nposition = 'p1'\n",
    )
    reading = readings.load(tmp_path)
    assert reading.spread is None
    assert reading.cards[0].position == "p1"


def test_position_and_an_unturned_card_round_trip_and_turned_true_is_never_written(tmp_path):
    cards = (
        ReadingCard("major_arcana.0", deck="rider-waite-smith", position="p1"),
        ReadingCard("major_arcana.1", deck="rider-waite-smith", position="p2", turned=False),
        ReadingCard("major_arcana.2", deck="rider-waite-smith"),
    )
    readings.save(tmp_path, sample(spread=snapshot(), cards=cards))

    written = table_of(tmp_path)["cards"]
    assert [entry.get("turned") for entry in written] == [None, False, None]
    assert "position" not in written[2]
    assert readings.load(tmp_path).cards == cards


def test_layout_is_parallel_to_the_cards(tmp_path):
    readings.save(tmp_path, sample())
    layout = table_of(tmp_path)["app"]["land.arcana.tarotcanvas"]["layout"]
    assert [entry["x"] for entry in layout] == [-180.0, 40.0]


def test_a_hand_written_reading_with_no_app_table_takes_default_geometry(tmp_path):
    write(
        tmp_path,
        "date = 2026-11-09\ndeck = 'rider-waite-smith'\n"
        "[[cards]]\nid = 'major_arcana.0'\n[[cards]]\nid = 'major_arcana.1'\nreversed = true\n",
    )
    reading = readings.load(tmp_path)

    assert reading.date == datetime(2026, 11, 9).astimezone()
    assert reading.cards == (
        ReadingCard("major_arcana.0", deck="rider-waite-smith", z=0.0),
        ReadingCard("major_arcana.1", reversed=True, deck="rider-waite-smith", z=1.0),
    )


def test_a_naive_date_is_local_time(tmp_path):
    write(tmp_path, "date = 2026-11-09T21:14:00\n")
    assert readings.load(tmp_path).date == datetime(2026, 11, 9, 21, 14).astimezone()


def test_a_card_with_no_id_is_skipped_and_its_neighbours_keep_their_layout(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(readings.logger, "warning", warnings.append)
    write(
        tmp_path,
        "date = 2026-11-09T21:14:00-08:00\n"
        "[[cards]]\nid = 'major_arcana.0'\n"
        "[[cards]]\nreversed = true\n"
        "[[cards]]\nid = 'major_arcana.2'\n"
        "[[app.'land.arcana.tarotcanvas'.layout]]\nx = 1.0\n"
        "[[app.'land.arcana.tarotcanvas'.layout]]\nx = 2.0\n"
        "[[app.'land.arcana.tarotcanvas'.layout]]\nx = 3.0\n",
    )
    cards = readings.load(tmp_path).cards

    assert [(card.id, card.x) for card in cards] == [
        ("major_arcana.0", 1.0),
        ("major_arcana.2", 3.0),
    ]
    assert len(warnings) == 1


@pytest.mark.parametrize(
    "text",
    [
        "date = [",
        "question = 'no date'\n",
        "date = 2026-11-09\ncards = 'not an array'\n",
        "date = 2026-11-09\n" + "x = " + "[" * 40 + "]" * 40 + "\n",
    ],
)
def test_an_unreadable_file_loads_as_none(tmp_path, monkeypatch, text):
    monkeypatch.setattr(readings.logger, "warning", lambda _: None)
    write(tmp_path, text)
    assert readings.load(tmp_path) is None


def test_a_missing_file_loads_as_none(tmp_path, monkeypatch):
    monkeypatch.setattr(readings.logger, "warning", lambda _: None)
    assert readings.load(tmp_path) is None


def test_a_reading_from_a_newer_build_still_loads(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(readings.logger, "warning", warnings.append)
    write(
        tmp_path,
        "date = 2026-11-09\n[[cards]]\nid = 'major_arcana.0'\n"
        "[app.'land.arcana.tarotcanvas']\nversion = 2\n",
    )
    assert readings.load(tmp_path).cards[0].id == "major_arcana.0"
    assert len(warnings) == 1


def test_scan_is_newest_first_and_skips_what_it_cannot_read(tmp_path, monkeypatch):
    monkeypatch.setattr(readings.logger, "warning", lambda _: None)
    older, newer = sample(date=WHEN - timedelta(days=1)), sample()
    readings.save(tmp_path / "200", older)
    readings.save(tmp_path / "100", newer)
    readings.save(tmp_path / "300.deleted", sample(date=WHEN + timedelta(days=1)))
    write(tmp_path / "400", "date = [")
    (tmp_path / "500").mkdir()
    (tmp_path / "200" / "1792423465_a_note.md").write_text("# Not a reading\n")

    assert readings.scan(tmp_path) == [(tmp_path / "100", newer), (tmp_path / "200", older)]


def test_scan_breaks_a_tie_by_the_newer_folder(tmp_path):
    readings.save(tmp_path / "100", sample())
    readings.save(tmp_path / "101", sample())
    assert [folder.name for folder, _ in readings.scan(tmp_path)] == ["101", "100"]


def test_scan_of_a_missing_base_is_empty(tmp_path):
    assert readings.scan(tmp_path / "nowhere") == []


def test_a_new_folder_is_named_by_the_time_and_steps_past_a_taken_one(tmp_path, monkeypatch):
    monkeypatch.setattr(toml_files.time, "time", lambda: 1000.5)
    assert readings.new_reading_dir(tmp_path) == tmp_path / "1000"
    assert readings.new_reading_dir(tmp_path) == tmp_path / "1001"


def test_a_failed_save_keeps_the_old_file_and_leaves_no_temporary(tmp_path, monkeypatch):
    readings.save(tmp_path, sample(question="old"))

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(toml_files.os, "replace", fail)
    with pytest.raises(OSError):
        readings.save(tmp_path, sample(question="new"))

    assert [entry.name for entry in tmp_path.iterdir()] == ["reading.toml"]
    assert readings.load(tmp_path).question == "old"


def test_the_events_singleton_is_stable():
    assert reading_events() is reading_events()
