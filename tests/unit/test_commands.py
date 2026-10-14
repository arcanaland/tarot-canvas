"""The registry is data, so what a key collision would break is checked before anything binds"""

import re

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget

from tarot_canvas.ui.commands import (
    ACTIVE_TOGETHER,
    COMMANDS,
    CONTEXTS,
    Scope,
    bind,
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


def test_every_id_is_unique_and_dotted():
    ids = [command.id for command in COMMANDS]
    assert len(ids) == len(set(ids))
    for command_id in ids:
        assert re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", command_id), command_id


def test_an_id_starts_with_its_scope():
    for command in COMMANDS:
        assert command.id.split(".")[0] == command.scope.value


def test_every_scope_says_its_context():
    assert set(CONTEXTS) == set(Scope)


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


def test_every_command_has_a_key_or_shows_one(qapp):
    for command in COMMANDS:
        assert keys_for(command.id) or command.shows, command.id


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


def test_what_a_menu_shows_is_a_command_that_has_a_key(qapp):
    for command in COMMANDS:
        if command.shows:
            assert keys_for(command.shows), command.id


def test_a_fixed_command_cannot_be_bound(qtbot):
    owner = QWidget()
    qtbot.addWidget(owner)
    for command in COMMANDS:
        if command.fixed:
            with pytest.raises(ValueError):
                bind(owner, command.scope, {command.id: lambda: None})


def test_a_command_is_bound_only_in_its_own_scope(qtbot):
    owner = QWidget()
    qtbot.addWidget(owner)
    with pytest.raises(ValueError):
        bind(owner, Scope.CANVAS, {"window.new_canvas": lambda: None})


def test_bind_keys_connects_and_adds_the_action(qtbot):
    owner = QWidget()
    qtbot.addWidget(owner)
    calls = []

    actions = bind(owner, Scope.CANVAS, {"canvas.fullscreen": lambda: calls.append(1)})

    action = actions["canvas.fullscreen"]
    assert action in owner.actions()
    assert action.shortcuts() == [QKeySequence("F")]
    assert action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    action.trigger()
    assert calls == [1]


def test_a_detached_command_is_left_off_its_owner(qtbot):
    owner = QWidget()
    qtbot.addWidget(owner)

    actions = bind(owner, Scope.WINDOW, {"window.quit": lambda: None}, detached={"window.quit"})

    assert actions["window.quit"] not in owner.actions()
    assert actions["window.quit"].shortcuts() == [QKeySequence("Ctrl+Q")]


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
