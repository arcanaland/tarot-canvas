import tomllib

import pytest

from tarot_canvas.models import spreads, toml_files
from tarot_canvas.models.spreads import Position, Spread


def sample():
    return Spread(
        name="The Horseshoe",
        description="Lay them left to right.\nRead them in order.",
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


def test_the_description_is_stored_under_that_key(tmp_path):
    spreads.save(tmp_path, sample())
    table = tomllib.loads((tmp_path / "spread.toml").read_text())
    assert table["description"] == sample().description


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

    monkeypatch.setattr(toml_files.os, "replace", fail)
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
    monkeypatch.setattr(toml_files.time, "time", lambda: 1000.5)
    assert spreads.new_spread_dir(tmp_path) == tmp_path / "1000"
    assert spreads.new_spread_dir(tmp_path) == tmp_path / "1001"
    assert (tmp_path / "1001").is_dir()


def test_the_next_id_is_past_the_largest_of_the_shape():
    assert spreads.next_position_id(["p1", "p3", "x"]) == "p4"
    assert spreads.next_position_id(["x", "p"]) == "p1"
    assert spreads.next_position_id([]) == "p1"


def write_spread(folder, text):
    folder.mkdir(exist_ok=True)
    (folder / spreads.SPREAD_FILE).write_text(text, encoding="utf-8")
    return folder


UNREADABLE = {
    "x is nan": '[[positions]]\nid = "p1"\nx = nan\n',
    "y is inf": '[[positions]]\nid = "p1"\ny = -inf\n',
    "rotation is nan": '[[positions]]\nid = "p1"\nrotation = nan\n',
    "z is inf": '[[positions]]\nid = "p1"\nz = inf\n',
    "nan as a string": '[[positions]]\nid = "p1"\nx = "nan"\n',
    "finite but past the limit": '[[positions]]\nid = "p1"\nx = 1e308\n',
    "too large for a float": f'[[positions]]\nid = "p1"\nx = {"9" * 400}\n',
    "nested past the parser": f"k = {'[' * 5000}{']' * 5000}\n",
    "nested past the writer": f"k = {'[' * 400}{']' * 400}\n",
}


@pytest.mark.parametrize("text", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_load_refuses_a_file_the_canvas_could_not_hold(tmp_path, text):
    with pytest.raises(ValueError):
        spreads.load(write_spread(tmp_path, text))


@pytest.mark.parametrize("text", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_scan_skips_a_file_the_canvas_could_not_hold(tmp_path, text):
    good = write_spread(tmp_path / "1", 'name = "good"\n')
    write_spread(tmp_path / "2", text)

    assert [folder for folder, _ in spreads.scan(tmp_path)] == [good]


def test_a_file_with_nesting_it_may_keep_survives_a_save(tmp_path):
    folder = write_spread(tmp_path / "in", "extra = { a = { b = [[1, 2], [3]] } }\n")
    out = tmp_path / "out"
    out.mkdir()

    spreads.save(out, spreads.load(folder))

    assert spreads.load(out).extra == {"extra": {"a": {"b": [[1, 2], [3]]}}}


def test_load_accepts_the_largest_numbers_it_allows(tmp_path):
    limit = toml_files.MAX_NUMBER
    folder = write_spread(
        tmp_path, f'[[positions]]\nid = "p1"\nx = {limit}\ny = {-limit}\nz = {limit}\n'
    )

    (position,) = spreads.load(folder).positions

    assert (position.x, position.y, position.z) == (limit, -limit, limit)


def test_a_spread_with_no_file_was_never_edited(tmp_path):
    assert spreads.edited_at(tmp_path) == 0.0


# -- the spreads that ship with the app


def test_no_included_root_is_no_included_spreads(included_base):
    assert not included_base.exists()
    assert spreads.scan_included() == []


def test_an_included_spread_is_listed_apart_from_the_users(included_base, spreads_base):
    included = included_base / "line"
    included.mkdir(parents=True)
    spreads.save(included, Spread("Shipped"))
    own = spreads.new_spread_dir()
    spreads.save(own, Spread("Mine"))

    assert [(folder, spread.name) for folder, spread in spreads.scan_included()] == [
        (included, "Shipped")
    ]
    assert [folder for folder, _ in spreads.scan()] == [own]
    assert spreads.is_included(included)
    assert not spreads.is_included(own)


def test_a_copy_of_an_included_spread_drops_only_its_sources(included_base, spreads_base):
    spread = Spread("A", description="d", sources=({"name": "A Book"},), extra={"k": 1})
    included = included_base / "line"
    included.mkdir(parents=True)

    assert spreads.copy_of(spread, included) == Spread("A", description="d", extra={"k": 1})
    assert spreads.copy_of(spread, spreads_base / "1") == spread
    assert spreads.copy_of(spread, None) == spread


@pytest.mark.parametrize("outside", ["../elsewhere", "../included-not", None])
def test_a_folder_outside_the_included_root_is_not_included(included_base, outside):
    included_base.mkdir()
    path = None if outside is None else included_base / outside

    assert not spreads.is_included(path)


def test_a_saved_spread_carries_the_apps_version(tmp_path):
    spreads.save(tmp_path, sample())
    table = tomllib.loads((tmp_path / "spread.toml").read_text())

    assert table["app"][spreads.APP_TABLE] == {"version": spreads.VERSION}


def test_a_file_with_no_version_loads_as_the_first(tmp_path):
    (tmp_path / "spread.toml").write_text("name = 'Old'\n")

    assert spreads.load(tmp_path) == Spread(name="Old")


def test_the_version_is_not_kept_as_an_unknown_key(tmp_path):
    spreads.save(tmp_path, sample())

    assert "app" not in spreads.load(tmp_path).extra


def test_other_keys_in_the_app_tables_survive_a_round_trip(tmp_path):
    folder = write_spread(
        tmp_path / "in",
        "name = 'A'\n"
        '[app."land.arcana.tarotcanvas"]\nversion = 1\nx_hint = 2\n'
        '[app."org.example.other"]\nversion = 7\n',
    )
    spread = spreads.load(folder)
    out = tmp_path / "out"
    out.mkdir()
    spreads.save(out, spread)

    assert tomllib.loads((out / "spread.toml").read_text())["app"] == {
        "land.arcana.tarotcanvas": {"x_hint": 2, "version": spreads.VERSION},
        "org.example.other": {"version": 7},
    }
    assert spreads.load(out) == spread


def test_a_spread_from_a_newer_build_is_refused(tmp_path):
    newer = spreads.VERSION + 1
    (tmp_path / "spread.toml").write_text(
        f'name = "A"\n[app."land.arcana.tarotcanvas"]\nversion = {newer}\n'
    )

    with pytest.raises(ValueError, match="newer"):
        spreads.load(tmp_path)


def test_a_spread_written_to_a_spec_is_refused(tmp_path):
    (tmp_path / "spread.toml").write_text('name = "A"\n[meta]\nschema_version = "1.0"\n')

    with pytest.raises(ValueError, match="spec"):
        spreads.load(tmp_path)


def test_scan_skips_a_spread_written_to_a_spec(tmp_path):
    write_spread(tmp_path / "1", '[meta]\nschema_version = "1.0"\n')
    write_spread(tmp_path / "2", 'name = "Ours"\n')

    assert [spread.name for _, spread in spreads.scan(tmp_path)] == ["Ours"]


def test_scan_skips_and_logs_a_spread_from_a_newer_build(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(spreads.logger, "warning", warnings.append)
    write_spread(
        tmp_path / "1",
        f'name = "A"\n[app."land.arcana.tarotcanvas"]\nversion = {spreads.VERSION + 1}\n',
    )

    assert spreads.scan(tmp_path) == []
    assert len(warnings) == 1
    assert "newer" in warnings[0]


@pytest.mark.parametrize(
    "text",
    [
        "app = 3\n",
        'app = { "land.arcana.tarotcanvas" = 3 }\n',
        '[app."land.arcana.tarotcanvas"]\nversion = "1"\n',
        '[app."land.arcana.tarotcanvas"]\nversion = true\n',
        '[app."land.arcana.tarotcanvas"]\nversion = 0\n',
        '[app."land.arcana.tarotcanvas"]\nversion = 1.0\n',
    ],
)
def test_a_malformed_version_is_a_value_error(tmp_path, text):
    (tmp_path / "spread.toml").write_text(text)
    with pytest.raises(ValueError):
        spreads.load(tmp_path)
