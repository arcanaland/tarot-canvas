"""Which parts of `tarot_canvas/ui/` may import which.

Each rule holds for the tree as it stands and fails on any new edge. An exemption is
named here, so widening a rule is a deliberate edit to this file.
"""

import ast
from pathlib import Path

import pytest

import tarot_canvas

UI = Path(tarot_canvas.__file__).parent / "ui"
PREFIX = "tarot_canvas.ui"

# What a generic widget may build on: the app's look and words, never its subjects.
FOUNDATIONS = {"typography", "palette", "strings", "units", "zoom_keys", "passage_metrics"}

# library -> tabs edges that are allowed.
LIBRARY_TO_TABS = {
    # The Library tab is a tab, and this is the contract every tab implements.
    ("library.tab", "tabs.base_tab"),
    # The notes cycle: the Notes view's pane reuses the card view's note rows.
    ("library.notes.details_pane", "tabs.card_view.notes_section"),
}


def module_name(path):
    rel = path.relative_to(UI).with_suffix("")
    parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
    return ".".join(parts)


def is_module(dotted):
    path = UI.joinpath(*dotted.split(".")) if dotted else UI
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def ui_imports(path):
    """Every `tarot_canvas.ui` module a file imports, relative to `ui`."""
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # `from tarot_canvas.ui import units` names a module, not a symbol
            targets = [
                f"{node.module}.{alias.name}"
                if is_module(f"{node.module}.{alias.name}"[len(PREFIX) + 1 :])
                else node.module
                for alias in node.names
            ]
        else:
            continue
        for target in targets:
            if target.startswith(PREFIX + "."):
                yield target[len(PREFIX) + 1 :]


EDGES = sorted(
    {(module_name(path), target) for path in UI.rglob("*.py") for target in ui_imports(path)}
)


def under(module, package):
    return module == package or module.startswith(package + ".")


def edges_from(package):
    return [(src, dst) for src, dst in EDGES if under(src, package)]


def test_the_walk_sees_the_tree():
    assert ("library.tab", "units") in EDGES


def test_widgets_import_only_widgets_and_foundations():
    wrong = [
        (src, dst)
        for src, dst in edges_from("widgets")
        if not under(dst, "widgets") and dst not in FOUNDATIONS
    ]
    assert wrong == []


def test_the_library_imports_no_tab_but_the_named_ones():
    wrong = [
        (src, dst)
        for src, dst in edges_from("library")
        if under(dst, "tabs") and (src, dst) not in LIBRARY_TO_TABS
    ]
    assert wrong == []


@pytest.mark.parametrize("package", ["covers", "catalog"])
def test_app_wide_services_import_no_screen(package):
    wrong = [
        (src, dst)
        for src, dst in edges_from(package)
        if any(under(dst, screen) for screen in ("library", "tabs", "windows"))
    ]
    assert wrong == []


# The Library's views, each a package. Decks is the one the others may use: every view that
# starts a reading offers its deck menu.
VIEWS = ("decks", "notes", "spreads", "esoterica", "readings")
SHARED_VIEW = "decks"


def view_of(module):
    parts = module.split(".")
    return parts[1] if len(parts) > 2 and parts[0] == "library" and parts[1] in VIEWS else None


def test_the_views_are_packages():
    assert all((UI / "library" / view / "__init__.py").is_file() for view in VIEWS)


def test_a_view_imports_no_other_view_but_decks():
    wrong = [
        (src, dst)
        for src, dst in edges_from("library")
        if view_of(src) and view_of(dst) not in (None, view_of(src), SHARED_VIEW)
    ]
    assert wrong == []
