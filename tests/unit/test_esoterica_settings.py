import pytest

from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.settings import (
    ESOTERICA_EXPANDED_KEY,
    ESOTERICA_HIDDEN_KEY,
    get_esoterica_expanded,
    get_esoterica_hidden,
    get_settings,
    set_esoterica_expanded,
    set_esoterica_hidden,
)

READERS = {
    ESOTERICA_EXPANDED_KEY: get_esoterica_expanded,
    ESOTERICA_HIDDEN_KEY: get_esoterica_hidden,
}


@pytest.mark.parametrize("key", READERS)
def test_nothing_stored_reads_as_an_empty_list(key):
    assert READERS[key]() == []


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("advice", ["advice"]),
        ("", []),
        (["advice", "group.suits"], ["advice", "group.suits"]),
        ([], []),
    ],
)
@pytest.mark.parametrize("key", READERS)
def test_whatever_shape_qsettings_hands_back_reads_as_a_list_of_strings(key, stored, expected):
    get_settings().setValue(key, stored)

    assert READERS[key]() == expected


@pytest.mark.parametrize(
    ("write", "read"),
    [
        (set_esoterica_expanded, get_esoterica_expanded),
        (set_esoterica_hidden, get_esoterica_hidden),
    ],
)
def test_writing_stores_the_list_and_emits_once(write, read):
    emitted = []
    connection = esoterica_events().display_changed.connect(lambda: emitted.append(read()))
    try:
        write(["symbols", "x_from_a_newer_version"])
    finally:
        esoterica_events().display_changed.disconnect(connection)

    assert emitted == [["symbols", "x_from_a_newer_version"]]
