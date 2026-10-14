from PyQt6.QtGui import QKeySequence

from tarot_canvas.settings import SHORTCUTS_PREFIX, get_settings
from tarot_canvas.ui.commands import (
    COMMANDS,
    Scope,
    by_id,
    conflicts,
    default_keys,
    is_bare_letter_or_digit,
    keys_for,
    menu_text,
    store_keys,
    tooltip_with_keys,
)


def test_every_id_is_unique():
    ids = [command.id for command in COMMANDS]
    assert len(ids) == len(set(ids))


def test_no_key_is_bound_twice_where_both_could_fire(qapp):
    assert conflicts({command.id: keys_for(command.id) for command in COMMANDS}) == []


def test_a_conflict_names_both_holders(qapp):
    keys = {"window.new_canvas": ["Ctrl+N"], "canvas.summon": ["Ctrl+N"], "card.cancel": ["D"]}
    assert conflicts(keys) == [("Ctrl+N", "window.new_canvas", "canvas.summon")]


def test_no_window_key_is_a_bare_letter_or_digit(qapp):
    for command in COMMANDS:
        if command.scope is not Scope.WINDOW:
            continue
        for key in keys_for(command.id):
            assert not is_bare_letter_or_digit(key), f"{command.id}: {key.toString()}"


def test_a_bare_letter_or_digit_is_one_without_ctrl_alt_or_meta(qapp):
    assert is_bare_letter_or_digit(QKeySequence("D"))
    assert is_bare_letter_or_digit(QKeySequence("Shift+7"))
    assert not is_bare_letter_or_digit(QKeySequence("Ctrl+D"))
    assert not is_bare_letter_or_digit(QKeySequence("F2"))
    assert not is_bare_letter_or_digit(QKeySequence())


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


def test_stored_keys_win_over_the_defaults(qapp):
    get_settings().setValue(SHORTCUTS_PREFIX + "canvas.summon", ["S", "Ctrl+Shift+S"])
    assert keys_for("canvas.summon") == [QKeySequence("S"), QKeySequence("Ctrl+Shift+S")]


def test_stored_keys_are_literal_on_macos(qapp):
    get_settings().setValue(SHORTCUTS_PREFIX + "window.tab_1", ["Alt+1"])
    assert keys_for("window.tab_1", platform="darwin") == [QKeySequence("Alt+1")]


def test_storing_no_keys_binds_none(qapp):
    store_keys("canvas.summon", [])
    assert get_settings().contains(SHORTCUTS_PREFIX + "canvas.summon")
    assert keys_for("canvas.summon") == []


def test_storing_the_defaults_forgets_them(qapp):
    store_keys("canvas.summon", ["S"])
    store_keys("canvas.summon", default_keys("canvas.summon"))
    assert not get_settings().contains(SHORTCUTS_PREFIX + "canvas.summon")
    assert keys_for("canvas.summon") == [QKeySequence("D")]
