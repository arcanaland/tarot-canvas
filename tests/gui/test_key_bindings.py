"""Every key the window binds, written out, so a change to how keys are bound changes none"""

from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QMenu, QToolBar, QToolButton

from tarot_canvas.ui.commands import COMMANDS
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.card_view.notes_tab import NotesTab
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.widgets.zoomable_image_view import ZoomableImageView

# Nearest first: the art and the Notes tab sit inside a card view
OWNERS = (
    (ZoomableImageView, "card_image"),
    (NotesTab, "notes"),
    (CardViewTab, "card"),
    (CanvasTab, "canvas"),
    (LibraryTab, "library"),
    (MainWindow, "window"),
)

W = "WindowShortcut"
WC = "WidgetWithChildrenShortcut"
WS = "WidgetShortcut"


def owner_of(obj):
    parent = obj.parent()
    while parent is not None:
        for cls, name in OWNERS:
            if isinstance(parent, cls):
                return name
        parent = parent.parent()
    return None


# They show an action's key; it is the widgets around them that the key works in
DISPLAYS = (QMenu, QToolBar, QToolButton)


def reach(obj):
    """Where a key is attached, those that only show it aside"""
    if isinstance(obj, QShortcut):
        widgets = [obj.parent()]
    else:
        widgets = [w for w in obj.associatedObjects() if not isinstance(w, DISPLAYS)]
    return ",".join(sorted(type(w).__name__ for w in widgets))


def bound_keys(window):
    """(owner, key, context, reach) for every key on every action and shortcut in the window"""
    found = []
    for obj in [*window.findChildren(QAction), *window.findChildren(QShortcut)]:
        if isinstance(obj, QAction):
            keys, context = obj.shortcuts(), obj.shortcutContext()
        else:
            keys, context = obj.keys(), obj.context()
        found += [
            (
                owner_of(obj),
                key.toString(QKeySequence.SequenceFormat.PortableText),
                context.name,
                reach(obj),
            )
            for key in keys
        ]
    return sorted(found)


def test_every_key_is_bound_as_it_was(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.new_canvas_tab()
    window.new_card_view_tab()
    window.new_library_tab()

    # The canvas's own Ctrl++, Ctrl+=, Ctrl+- and Ctrl+0 are gone: View > Zoom reaches it.
    # Del on the canvas and in the Notes list is Edit > Delete's.
    # Read on Linux; the standard keys (Copy, Zoom In, Settings…) are its bindings for them
    expected = [
        ("canvas", "Backspace", W, "CanvasTab"),
        ("canvas", "Ctrl+Alt+A", W, "CanvasTab"),
        ("canvas", "Ctrl+[", W, "CanvasTab"),
        ("canvas", "Ctrl+]", W, "CanvasTab"),
        ("canvas", "D", W, "CanvasTab"),
        ("canvas", "Esc", W, "CanvasTab"),
        ("canvas", "F", WC, "CanvasTab"),
        ("canvas", "R", W, "CanvasTab"),
        ("canvas", "Shift+F", W, "CanvasTab"),
        ("card", "Ctrl+I", WC, "CardViewTab"),
        ("card", "Esc", WC, "CardViewTab"),
        ("card_image", "Backspace", WC, "ZoomableImageView"),
        ("card_image", "D", WC, "ZoomableImageView"),
        ("card_image", "End", WC, "ZoomableImageView"),
        ("card_image", "F", WC, "ZoomableImageView"),
        ("card_image", "Home", WC, "ZoomableImageView"),
        ("card_image", "I", WC, "ZoomableImageView"),
        ("card_image", "PgDown", WC, "ZoomableImageView"),
        ("card_image", "PgUp", WC, "ZoomableImageView"),
        ("card_image", "Space", WC, "ZoomableImageView"),
        ("card_image", "[", WC, "ZoomableImageView"),
        ("card_image", "]", WC, "ZoomableImageView"),
        ("library", "Ctrl+I", WC, "LibraryTab"),
        # Dismiss keys inside a widget, not commands
        ("library", "Esc", WS, "QListView"),
        ("library", "Esc", WS, "QListView"),
        ("library", "Esc", WS, "QListView"),
        ("notes", "F2", WC, "QListView"),
        ("window", "Alt+1", W, "MainWindow"),
        ("window", "Alt+2", W, "MainWindow"),
        ("window", "Alt+3", W, "MainWindow"),
        ("window", "Alt+4", W, "MainWindow"),
        ("window", "Alt+5", W, "MainWindow"),
        ("window", "Alt+6", W, "MainWindow"),
        ("window", "Alt+7", W, "MainWindow"),
        ("window", "Alt+8", W, "MainWindow"),
        ("window", "Alt+9", W, "MainWindow"),
        ("window", "Copy", W, "MainWindow"),
        ("window", "Ctrl++", W, "MainWindow"),
        ("window", "Ctrl+-", W, "MainWindow"),
        ("window", "Ctrl+0", W, "MainWindow"),
        ("window", "Ctrl+=", W, "MainWindow"),
        ("window", "Ctrl+A", W, "MainWindow"),
        ("window", "Ctrl+C", W, "MainWindow"),
        ("window", "Ctrl+E", W, ""),
        ("window", "Ctrl+F", W, "MainWindow"),
        ("window", "Ctrl+Ins", W, "MainWindow"),
        ("window", "Ctrl+L", W, ""),
        ("window", "Ctrl+N", W, ""),
        ("window", "Ctrl+O", W, ""),
        ("window", "Ctrl+P", W, "MainWindow"),
        ("window", "Ctrl+Q", W, ""),
        ("window", "Ctrl+Shift+A", W, "MainWindow"),
        ("window", "Ctrl+Shift+F", W, "MainWindow"),
        ("window", "Ctrl+T", W, ""),
        ("window", "Ctrl+V", W, "MainWindow"),
        ("window", "Ctrl+W", W, ""),
        ("window", "Ctrl+X", W, "MainWindow"),
        ("window", "Cut", W, "MainWindow"),
        ("window", "Del", W, "MainWindow"),
        ("window", "F11", W, "MainWindow"),
        ("window", "Find", W, "MainWindow"),
        ("window", "Paste", W, "MainWindow"),
        ("window", "Settings", W, ""),
        ("window", "Shift+Del", W, "MainWindow"),
        ("window", "Shift+Ins", W, "MainWindow"),
        ("window", "Zoom In", W, "MainWindow"),
        ("window", "Zoom Out", W, "MainWindow"),
    ]

    assert bound_keys(window) == expected

    # And every command the registry binds is bound, the Go entries' included
    bound = {action.objectName() for action in window.findChildren(QAction)}
    assert {command.id for command in COMMANDS if not command.fixed} <= bound

    # The canvas's timers must not outlive it
    qtbot.wait(1100)
