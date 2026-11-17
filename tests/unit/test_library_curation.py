import tomllib

import pytest

from tarot_canvas.models import library_curation as curation
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.settings import get_settings

LEGACY = curation.LEGACY_ESOTERICA_DISABLED_KEY


def stored(file):
    with open(file, "rb") as handle:
        return tomllib.load(handle)


@pytest.fixture
def emitted():
    """Which of the three views' signals fired"""
    fired = []
    connections = [
        (signal, signal.connect(lambda name=name: fired.append(name)))
        for name, signal in (
            ("spreads", spread_events().spreads_changed),
            ("readings", reading_events().readings_changed),
            ("esoterica", esoterica_events().sources_changed),
        )
    ]
    yield fired
    for signal, connection in connections:
        signal.disconnect(connection)


def test_no_file_is_nothing_curated(curation_file):
    assert not curation_file.exists()
    assert curation.spread_pins() == set()
    assert curation.reading_pins() == set()
    assert curation.esoterica_disabled() == []


def test_a_pin_is_the_folder_name_in_its_views_table(curation_file, spreads_base, emitted):
    curation.set_reading_pinned(spreads_base.parent / "readings" / "1731500000", True)
    curation.set_spread_pinned(spreads_base / "1731400000", True)

    assert stored(curation_file) == {
        "readings": {"pinned": ["1731500000"]},
        "spreads": {"pinned": ["1731400000"]},
    }
    assert emitted == ["readings", "spreads"]


def test_an_included_spread_is_keyed_under_included(included_base):
    folder = included_base / "celtic-cross"
    folder.mkdir(parents=True)

    assert curation.spread_key(folder) == "included/celtic-cross"


def test_pinning_twice_writes_once_and_unpinning_empties_the_table(curation_file, emitted):
    curation.set_reading_pinned("/x/1", True)
    curation.set_reading_pinned("/x/1", True)
    curation.set_reading_pinned("/x/1", False)

    assert emitted == ["readings", "readings"]
    assert stored(curation_file) == {}


def test_pinning_a_hidden_spread_unhides_it_and_hiding_unpins_it(curation_file, included_base):
    folder = included_base / "horseshoe"
    folder.mkdir(parents=True)

    curation.set_spread_hidden(folder, True)
    assert curation.spread_hides() == {"included/horseshoe"}

    curation.set_spread_pinned(folder, True)
    assert (curation.spread_pins(), curation.spread_hides()) == ({"included/horseshoe"}, set())

    curation.set_spread_hidden(folder, True)
    assert (curation.spread_pins(), curation.spread_hides()) == (set(), {"included/horseshoe"})


def test_a_spread_of_the_users_own_is_never_hidden(curation_file, spreads_base, emitted):
    curation.set_spread_hidden(spreads_base / "1731400000", True)

    assert curation.spread_hides() == set()
    assert emitted == []


def test_keys_with_nothing_behind_them_and_unknown_tables_are_kept(curation_file):
    curation_file.write_text(
        '[readings]\npinned = ["from-another-machine"]\n'
        '[decks]\nfuture = ["kept"]\n'
        '[spreads]\nhidden = ["included/gone"]\nsorted_by = "kept too"\n'
    )

    curation.set_reading_pinned("/x/1731500000", True)

    assert stored(curation_file) == {
        "readings": {"pinned": ["from-another-machine", "1731500000"]},
        "decks": {"future": ["kept"]},
        "spreads": {"hidden": ["included/gone"], "sorted_by": "kept too"},
    }


def test_forgetting_a_deleted_item_removes_only_its_key(curation_file, spreads_base):
    curation.set_spread_pinned(spreads_base / "1", True)
    curation.set_spread_pinned(spreads_base / "2", True)
    curation.set_reading_pinned("/x/3", True)

    curation.forget_spread(spreads_base / "1")
    curation.forget_reading("/x/3")

    assert stored(curation_file) == {"spreads": {"pinned": ["2"]}}


def test_an_unreadable_file_reads_as_empty_and_is_left_until_the_user_changes_something(
    curation_file,
):
    curation_file.write_text("[readings\npinned = [")

    assert curation.reading_pins() == set()
    curation.forget_reading("/x/1")  # changes nothing, so writes nothing
    assert curation_file.read_text() == "[readings\npinned = ["

    curation.set_reading_pinned("/x/1", True)
    assert stored(curation_file) == {"readings": {"pinned": ["1"]}}


def test_a_hand_edit_is_read_without_restarting(curation_file):
    assert curation.reading_pins() == set()

    curation_file.write_text('[readings]\npinned = ["1", 2, "3"]\n')

    assert curation.reading_pins() == {"1", "3"}


# -- esoterica's disabled sources, moved out of QSettings --------------------------------


def test_disabling_writes_the_list_and_says_the_sources_changed(curation_file, emitted):
    curation.set_esoterica_disabled(["land.arcana/mcelroy", "x/unknown"])

    assert stored(curation_file) == {
        "esoterica": {"disabled": ["land.arcana/mcelroy", "x/unknown"]}
    }
    assert curation.esoterica_disabled() == ["land.arcana/mcelroy", "x/unknown"]
    assert emitted == ["esoterica"]


def test_qsettings_list_is_carried_over_once_with_identifiers_nothing_read(curation_file):
    get_settings().setValue(LEGACY, ["x/from-another-machine", "land.arcana/mcelroy"])

    assert curation.esoterica_disabled() == ["x/from-another-machine", "land.arcana/mcelroy"]
    assert stored(curation_file) == {
        "esoterica": {"disabled": ["x/from-another-machine", "land.arcana/mcelroy"]}
    }
    assert not get_settings().contains(LEGACY)


@pytest.mark.parametrize("legacy", ["one/source", ["one/source"]])
def test_whatever_shape_qsettings_held_is_carried(curation_file, legacy):
    get_settings().setValue(LEGACY, legacy)

    assert curation.esoterica_disabled() == ["one/source"]


def test_an_empty_qsettings_list_is_removed_without_a_file(curation_file):
    get_settings().setValue(LEGACY, [])

    assert curation.esoterica_disabled() == []
    assert not curation_file.exists()
    assert not get_settings().contains(LEGACY)


def test_the_file_wins_over_a_qsettings_list_it_already_holds(curation_file):
    curation_file.write_text('[esoterica]\ndisabled = ["from/the-file"]\n')
    get_settings().setValue(LEGACY, ["from/qsettings"])

    assert curation.esoterica_disabled() == ["from/the-file"]
    assert not get_settings().contains(LEGACY)


def test_an_unreadable_file_keeps_the_qsettings_list_in_force(curation_file):
    curation_file.write_text("not = [toml")
    get_settings().setValue(LEGACY, ["one/source"])

    assert curation.esoterica_disabled() == ["one/source"]
    assert curation_file.read_text() == "not = [toml"
    assert get_settings().contains(LEGACY)


def test_a_failed_write_leaves_the_qsettings_list_to_retry(curation_file, monkeypatch):
    get_settings().setValue(LEGACY, ["one/source"])

    write, failing = curation.write_toml, [True]

    def flaky(*args):
        if failing[0]:
            raise OSError("read-only")
        write(*args)

    monkeypatch.setattr(curation, "write_toml", flaky)
    assert curation.esoterica_disabled() == ["one/source"]
    assert get_settings().contains(LEGACY)

    failing[0] = False
    assert curation.esoterica_disabled() == ["one/source"]
    assert not get_settings().contains(LEGACY)


def test_turning_every_source_back_on_retires_the_qsettings_list(curation_file):
    get_settings().setValue(LEGACY, ["one/source"])

    curation.set_esoterica_disabled([])

    assert curation.esoterica_disabled() == []
    assert not get_settings().contains(LEGACY)
