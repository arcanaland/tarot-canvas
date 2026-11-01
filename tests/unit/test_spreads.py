import tomllib

import pytest

from tarot_canvas.models import spreads
from tarot_canvas.models.spreads import Position, Spread


def sample():
    return Spread(
        name="The Horseshoe",
        usage="Lay them left to right.\nRead them in order.",
        sources=({"url": "https://example.org/a", "author": "Someone"}, {"note": "Only a note"}),
        positions=(
            Position("p1", "Past", "What led here", -1.5, 0.0, 0.0, 1.0, {"x_colour": "red"}),
            Position("p3", "", "", 1.5, 0.25, 90.0, 2.0),
        ),
        extra={"x_tradition": "Golden Dawn"},
    )


def test_a_spread_survives_a_round_trip_with_its_unknown_keys(tmp_path):
    spreads.save(tmp_path, sample())
    assert spreads.load(tmp_path) == sample()


def test_position_order_is_kept(tmp_path):
    spreads.save(tmp_path, sample())
    table = tomllib.loads((tmp_path / "spread.toml").read_text())
    assert [position["id"] for position in table["positions"]] == ["p1", "p3"]


def test_an_empty_spread_survives_a_round_trip(tmp_path):
    spreads.save(tmp_path, Spread())
    assert spreads.load(tmp_path) == Spread()


def test_saving_replaces_the_file_and_leaves_no_temporary(tmp_path):
    (tmp_path / "spread.toml").write_text("name = 'old'\n")
    spreads.save(tmp_path, sample())
    assert [entry.name for entry in tmp_path.iterdir()] == ["spread.toml"]
    assert spreads.load(tmp_path).name == "The Horseshoe"


def test_a_failed_save_keeps_the_old_file_and_leaves_no_temporary(tmp_path, monkeypatch):
    (tmp_path / "spread.toml").write_text("name = 'old'\n")

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(spreads.os, "replace", fail)
    with pytest.raises(OSError):
        spreads.save(tmp_path, sample())

    assert [entry.name for entry in tmp_path.iterdir()] == ["spread.toml"]
    assert spreads.load(tmp_path).name == "old"


def test_scan_skips_and_logs_a_folder_it_cannot_read(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(spreads.logger, "warning", warnings.append)
    (tmp_path / "1").mkdir()
    spreads.save(tmp_path / "1", sample())
    (tmp_path / "2").mkdir()
    (tmp_path / "2" / "spread.toml").write_text("name = [")
    (tmp_path / "3").mkdir()

    assert spreads.scan(tmp_path) == [(tmp_path / "1", sample())]
    assert len(warnings) == 2
    assert "2" in warnings[0]


@pytest.mark.parametrize(
    "text",
    [
        "[[positions]]\nlabel = 'no id'\n",
        "[[positions]]\nid = 'p1'\nx = 'left'\n",
        "positions = [1]\n",
        "sources = [1]\n",
    ],
)
def test_a_malformed_spread_is_a_value_error(tmp_path, text):
    (tmp_path / "spread.toml").write_text(text)
    with pytest.raises(ValueError):
        spreads.load(tmp_path)


def test_scan_of_a_missing_base_is_empty(tmp_path):
    assert spreads.scan(tmp_path / "nowhere") == []


def test_a_new_folder_is_named_by_the_time_and_steps_past_a_taken_one(tmp_path, monkeypatch):
    monkeypatch.setattr(spreads.time, "time", lambda: 1000.5)
    assert spreads.new_spread_dir(tmp_path) == tmp_path / "1000"
    assert spreads.new_spread_dir(tmp_path) == tmp_path / "1001"
    assert (tmp_path / "1001").is_dir()


def test_the_next_id_is_past_the_largest_of_the_shape():
    assert spreads.next_position_id(["p1", "p3", "x"]) == "p4"
    assert spreads.next_position_id(["x", "p"]) == "p1"
    assert spreads.next_position_id([]) == "p1"
