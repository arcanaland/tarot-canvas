import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

from tarot_canvas.ui.commands import (
    ACTIVE_TOGETHER,
    COMMANDS,
    Scope,
    by_id,
    keys_for,
    menu_text,
    tooltip_with_keys,
)

MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.MetaModifier
)


def test_every_id_is_unique():
    ids = [command.id for command in COMMANDS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "scopes", ACTIVE_TOGETHER, ids=lambda s: "+".join(sorted(x.value for x in s))
)
def test_no_key_is_bound_twice_where_both_could_fire(qapp, scopes):
    seen = {}
    for command in COMMANDS:
        if command.scope not in scopes:
            continue
        for key in keys_for(command.id):
            text = key.toString(QKeySequence.SequenceFormat.PortableText)
            assert text not in seen, f"{text}: {seen.get(text)} and {command.id}"
            seen[text] = command.id


def test_no_window_key_is_a_bare_letter_or_digit(qapp):
    for command in COMMANDS:
        if command.scope is not Scope.WINDOW:
            continue
        for key in keys_for(command.id):
            combination = key[0]
            code = combination.key().value
            bare = not combination.keyboardModifiers() & MODIFIERS
            alnum = Qt.Key.Key_A.value <= code <= Qt.Key.Key_Z.value or (
                Qt.Key.Key_0.value <= code <= Qt.Key.Key_9.value
            )
            assert not (bare and alnum), f"{command.id}: {key.toString()}"


def test_option_and_a_digit_is_cmd_on_macos(qapp):
    assert keys_for("window.tab_1", platform="darwin") == [QKeySequence("Ctrl+1")]
    assert keys_for("window.tab_1", platform="linux") == [QKeySequence("Alt+1")]


def test_a_tooltip_takes_its_key_from_the_command(qapp):
    assert tooltip_with_keys("Summon", "canvas.summon") == "Summon (D)"
    assert tooltip_with_keys("Nothing", "window.go_next") == "Nothing"
    # Words not yet written stay unwritten
    assert tooltip_with_keys("", "library.toggle_details") == ""


def test_a_menu_entry_shows_the_key_it_mirrors(qapp):
    assert menu_text("Next", by_id("window.go_next").shows) == "Next\tRight"
