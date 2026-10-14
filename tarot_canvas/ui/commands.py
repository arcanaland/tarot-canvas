"""Every command the app binds a key to"""

import re
import sys
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import get_shortcut_keys, set_shortcut_keys
from tarot_canvas.ui.commands_text import COMMANDS_TEXT
from tarot_canvas.ui.notes_text import NOTES_TEXT
from tarot_canvas.ui.windows.preferences_text import PREFERENCES_TEXT

StandardKey = QKeySequence.StandardKey


class Scope(Enum):
    WINDOW = "window"
    CANVAS = "canvas"
    CARD = "card"  # the card view tab
    CARD_IMAGE = "card_image"
    NOTES = "notes"
    LIBRARY = "library"


CONTEXTS = {
    Scope.WINDOW: Qt.ShortcutContext.WindowShortcut,
    Scope.CANVAS: Qt.ShortcutContext.WindowShortcut,
    Scope.CARD: Qt.ShortcutContext.WidgetWithChildrenShortcut,
    Scope.CARD_IMAGE: Qt.ShortcutContext.WidgetWithChildrenShortcut,
    Scope.NOTES: Qt.ShortcutContext.WidgetWithChildrenShortcut,
    Scope.LIBRARY: Qt.ShortcutContext.WidgetWithChildrenShortcut,
}

# Scopes whose keys can fire at the same moment, so no key may be in two of one set
ACTIVE_TOGETHER = (
    frozenset({Scope.WINDOW, Scope.CANVAS}),
    frozenset({Scope.WINDOW, Scope.CARD, Scope.CARD_IMAGE}),
    frozenset({Scope.WINDOW, Scope.CARD, Scope.NOTES}),
    frozenset({Scope.WINDOW, Scope.LIBRARY}),
)


@dataclass(frozen=True)
class Command:
    id: str
    text: str | None
    icon: str | None
    defaults: tuple[str | StandardKey, ...]
    scope: Scope
    # Handled in a keyPressEvent not by an action
    fixed: bool = False
    # Only where it differs from the scope's
    context: Qt.ShortcutContext | None = None
    # Another command whose key a menu entry displays after its label, binding none itself
    shows: str | None = None


def _command(id, text, icon, defaults, scope, **kwargs):
    return Command(id, text, icon, tuple(defaults), scope, **kwargs)


W, CV, C, CI, N, L = (
    Scope.WINDOW,
    Scope.CANVAS,
    Scope.CARD,
    Scope.CARD_IMAGE,
    Scope.NOTES,
    Scope.LIBRARY,
)
T = COMMANDS_TEXT

COMMANDS = (
    # File
    _command("window.new_canvas", T["new_canvas"], "draw-rectangle", ["Ctrl+N"], W),
    _command("window.new_library", T["new_library"], "view-list-icons", ["Ctrl+L"], W),
    _command("window.new_card_view", T["new_card_view"], "view-pages-single", ["Ctrl+T"], W),
    _command("window.open_deck", T["open_deck"], "document-open-folder", ["Ctrl+O"], W),
    _command("window.close_tab", T["close_tab"], "tab-close", ["Ctrl+W"], W),
    _command("window.quit", T["quit"], "application-exit", ["Ctrl+Q"], W),
    # Edit
    _command("window.cut", T["cut"], "edit-cut", [StandardKey.Cut], W),
    _command("window.copy_card", T["copy_card"], "edit-copy", [StandardKey.Copy], W),
    _command("window.paste_card", T["paste_card"], "edit-paste", [StandardKey.Paste], W),
    _command("window.delete", T["delete"], "edit-delete", [StandardKey.Delete], W),
    _command("window.select_all", T["select_all"], "edit-select-all", [StandardKey.SelectAll], W),
    _command("window.deselect", T["deselect"], "edit-select-none", ["Ctrl+Shift+A"], W),
    _command("window.find", T["find"], "edit-find", [StandardKey.Find], W),
    # View
    _command("window.card_explorer", T["card_explorer"], "view-sidetree", ["Ctrl+E"], W),
    _command("window.fullscreen", T["fullscreen"], "view-fullscreen", ["Ctrl+Shift+F", "F11"], W),
    # + shares a key with = on many layouts, so the unshifted press zooms too
    _command(
        "window.zoom_in", PREFERENCES_TEXT["zoom_in"], "zoom-in", [StandardKey.ZoomIn, "Ctrl+="], W
    ),
    _command("window.zoom_out", PREFERENCES_TEXT["zoom_out"], "zoom-out", [StandardKey.ZoomOut], W),
    _command("window.reset_zoom", PREFERENCES_TEXT["reset_zoom"], "zoom-original", ["Ctrl+0"], W),
    # Go: the keys are the art's, so these only show them
    _command(
        "window.go_previous",
        T["go_previous"],
        "go-previous",
        [],
        W,
        shows="card_image.previous_or_pan",
    ),
    _command("window.go_next", T["go_next"], "go-next", [], W, shows="card_image.next_or_pan"),
    _command("window.go_first", T["go_first"], "go-first", [], W, shows="card_image.first"),
    _command("window.go_last", T["go_last"], "go-last", [], W, shows="card_image.last"),
    _command("window.go_random", T["go_random"], "roll", [], W, shows="card_image.random"),
    _command(
        "window.go_previous_deck",
        T["go_previous_deck"],
        "go-previous-skip",
        [],
        W,
        shows="card_image.previous_deck",
    ),
    _command(
        "window.go_next_deck",
        T["go_next_deck"],
        "go-next-skip",
        [],
        W,
        shows="card_image.next_deck",
    ),
    _command("window.find_card", T["find_card"], "edit-find", ["Ctrl+P"], W),
    # Settings
    _command(
        "window.preferences",
        PREFERENCES_TEXT["configure"],
        "configure",
        [StandardKey.Preferences],
        W,
    ),
    # Alt+1 to Alt+9 pick a tab by position
    *(
        _command(f"window.tab_{n}", T["tab_n"].format(n=n), None, [f"Alt+{n}"], W)
        for n in range(1, 10)
    ),
    # Canvas
    _command("canvas.summon", T["summon_card"], "document-new", ["D"], CV),
    _command("canvas.flip", T["flip_card"], "object-flip-vertical", ["R"], CV),
    _command("canvas.delete", T["delete_card"], "edit-delete", ["Backspace"], CV),
    _command("canvas.bring_to_front", T["bring_to_front"], "go-top", ["Ctrl+]"], CV),
    _command("canvas.send_to_back", T["send_to_back"], "go-bottom", ["Ctrl+["], CV),
    _command("canvas.align", T["align_cards"], "align-horizontal-center", ["Ctrl+Alt+A"], CV),
    _command("canvas.fit", T["fit_all"], "zoom-fit-best", ["Shift+F"], CV),
    # A bare F
    _command(
        "canvas.fullscreen",
        T["fullscreen_canvas"],
        "view-fullscreen",
        ["F"],
        CV,
        context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
    ),
    _command("canvas.cancel", T["cancel_selection"], None, ["Esc"], CV),
    # Card view
    _command("card.toggle_details", T["card_toggle_details"], None, ["Ctrl+I"], C),
    _command("card.cancel", T["card_cancel"], None, ["Esc"], C),
    # Card art: bare keys, so typing in the details pane is left alone
    _command("card_image.fullscreen", T["fullscreen"], None, ["F"], CI),
    _command("card_image.toggle_details", T["card_image_toggle_details"], None, ["I"], CI),
    _command("card_image.previous", T["go_previous"], None, ["PgUp", "Backspace"], CI),
    _command("card_image.next", T["go_next"], None, ["PgDown", "Space"], CI),
    _command("card_image.first", T["go_first"], None, ["Home"], CI),
    _command("card_image.last", T["go_last"], None, ["End"], CI),
    _command("card_image.previous_deck", T["go_previous_deck"], None, ["["], CI),
    _command("card_image.next_deck", T["go_next_deck"], None, ["]"], CI),
    _command("card_image.random", T["go_random"], None, ["D"], CI),
    # Left and Right pan a zoomed card, so the view decides
    _command("card_image.previous_or_pan", T["go_previous"], None, ["Left"], CI, fixed=True),
    _command("card_image.next_or_pan", T["go_next"], None, ["Right"], CI, fixed=True),
    # Notes
    _command("notes.rename", NOTES_TEXT["rename"], "edit-rename", ["F2"], N),
    _command("notes.delete", NOTES_TEXT["delete"], "edit-delete", [], N, shows="window.delete"),
    # Library
    _command("library.toggle_details", T["library_toggle_details"], None, ["Ctrl+I"], L),
)

_BY_ID = {command.id: command for command in COMMANDS}


def by_id(command_id):
    return _BY_ID[command_id]


# On macOS Option+digit types a character, so it is Cmd there
_OPTION_DIGIT = re.compile(r"^Alt\+(\d)$")


def _expand(default, platform):
    if isinstance(default, StandardKey):
        return list(QKeySequence.keyBindings(default))
    if platform == "darwin":
        default = _OPTION_DIGIT.sub(r"Ctrl+\1", default)
    return [QKeySequence(default)]


def default_keys(command_id, platform=sys.platform):
    keys = []
    for default in by_id(command_id).defaults:
        keys += [key for key in _expand(default, platform) if key not in keys]
    return keys


def keys_for(command_id, platform=sys.platform):
    """The keys in force for a command, first the one to show"""
    stored = get_shortcut_keys(command_id)
    if stored is None:
        return default_keys(command_id, platform)
    keys = []
    for text in stored:
        key = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
        if not key.isEmpty() and key not in keys:
            keys.append(key)
    return keys


def portable(keys):
    """Keys as the text they are stored and compared in"""
    return tuple(
        key if isinstance(key, str) else key.toString(QKeySequence.SequenceFormat.PortableText)
        for key in keys
    )


def store_keys(command_id, keys):
    """Store a command's keys, forgetting them when they are its defaults"""
    keys = portable(keys)
    set_shortcut_keys(command_id, None if keys == portable(default_keys(command_id)) else keys)


def conflicts(keys_by_id):
    """(key, holder, other) for each key two commands hold where both could fire"""
    found = {}
    for scopes in ACTIVE_TOGETHER:
        holders = {}
        for command_id, keys in keys_by_id.items():
            if by_id(command_id).scope not in scopes:
                continue
            for key in portable(keys):
                holder = holders.setdefault(key, command_id)
                if holder != command_id:
                    found[(key, holder, command_id)] = None
    return list(found)


_MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.MetaModifier
)


def is_bare_letter_or_digit(key):
    """A key that types a character, so no window command may take it"""
    if key.isEmpty():
        return False
    combination = key[0]
    code = combination.key().value
    bare = not combination.keyboardModifiers() & _MODIFIERS
    alnum = Qt.Key.Key_A.value <= code <= Qt.Key.Key_Z.value or (
        Qt.Key.Key_0.value <= code <= Qt.Key.Key_9.value
    )
    return bool(bare and alnum)


def key_text(command):
    """The first key of an action or a command id"""
    keys = command.shortcuts() if isinstance(command, QAction) else keys_for(command)
    return keys[0].toString(QKeySequence.SequenceFormat.NativeText) if keys else ""


def tooltip_with_keys(words, command):
    key = key_text(command)
    return f"{words} ({key})" if words and key else words


def menu_text(words, command):
    """A menu label showing a key it does not bind"""
    key = key_text(command)
    return f"{words}\t{key}" if key else words


# Dynamic properties holding (words, command id), so apply_shortcuts can re-render the text
_TOOLTIP_KEYS = "tooltip_with_keys"
_MENU_KEYS = "menu_text"


def _id_of(command):
    return command.objectName() if isinstance(command, QAction) else command


def set_tooltip_with_keys(target, words, command):
    """A tooltip naming command's key, kept current by apply_shortcuts; None names none"""
    if command is None:
        target.setProperty(_TOOLTIP_KEYS, None)
        target.setToolTip(words)
        return
    target.setProperty(_TOOLTIP_KEYS, (words, _id_of(command)))
    target.setToolTip(tooltip_with_keys(words, _id_of(command)))


def set_menu_text(action, words, command):
    """An action's text showing command's key, kept current by apply_shortcuts"""
    action.setProperty(_MENU_KEYS, (words, _id_of(command)))
    action.setText(menu_text(words, _id_of(command)))


def apply_shortcuts():
    """Re-key every bound action and re-render every text that shows a key"""
    for window in QApplication.topLevelWidgets():
        for obj in [window, *window.findChildren(QObject)]:
            if isinstance(obj, QAction) and obj.objectName() in _BY_ID:
                obj.setShortcuts(keys_for(obj.objectName()))
            if (shown := obj.property(_TOOLTIP_KEYS)) is not None:
                obj.setToolTip(tooltip_with_keys(*shown))
            if (shown := obj.property(_MENU_KEYS)) is not None:
                obj.setText(menu_text(*shown))


def bind(owner, scope, handlers, *, detached=(), platform=sys.platform):
    """An action on owner for each command in handlers, keyed and connected to it"""
    actions = {}
    for command_id, handler in handlers.items():
        command = by_id(command_id)
        if command.scope is not scope:
            raise ValueError(f"{command_id} is not in {scope}")
        if command.fixed:
            raise ValueError(f"{command_id} is fixed: a view handles its key")

        action = QAction(command.text or "", owner)
        action.setObjectName(command.id)
        if command.shows:
            set_menu_text(action, command.text or "", command.shows)
        if command.icon:
            action.setIcon(QIcon.fromTheme(command.icon))
        action.setShortcuts(keys_for(command_id, platform))
        action.setShortcutContext(command.context or CONTEXTS[scope])
        # Handlers take nothing
        action.triggered.connect(lambda _checked=False, handler=handler: handler())
        if command_id not in detached:
            owner.addAction(action)
        actions[command_id] = action
    return actions
