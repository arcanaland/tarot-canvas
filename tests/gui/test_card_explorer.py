from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QAbstractItemView

from tarot_canvas.ui.card_explorer import CardExplorerPanel
from tarot_canvas.ui.card_transfer import CARD_MIME, card_from_mime


def panel(qtbot, platform="linux"):
    widget = CardExplorerPanel(platform=platform)
    qtbot.addWidget(widget)
    return widget


def widest_row(explorer):
    """The widest label in the tree, indented by its depth, measured by hand."""
    metrics = QFontMetrics(explorer.tree_view.font())
    indent = explorer.tree_view.indentation()
    model = explorer.model
    widest = 0
    for i in range(model.rowCount()):
        group = model.item(i)
        rows = [(group.text(), 1)] + [(group.child(j).text(), 2) for j in range(group.rowCount())]
        for text, depth in rows:
            widest = max(widest, metrics.horizontalAdvance(text) + depth * indent)
    return widest


def test_preferred_width_fits_the_widest_card_name(qtbot):
    explorer = panel(qtbot)
    assert explorer.preferred_width() >= widest_row(explorer)
    assert explorer.preferred_width() <= widest_row(explorer) + 40


def test_preferred_width_stays_within_the_panels_own_bounds(qtbot):
    explorer = panel(qtbot)

    assert explorer.minimumSizeHint().width() <= explorer.preferred_width()
    assert explorer.preferred_width() <= explorer.maximumWidth()


def test_the_close_button_asks_to_be_closed(qtbot):
    explorer = panel(qtbot)
    with qtbot.waitSignal(explorer.close_requested, timeout=1000):
        explorer.close_button.click()


def test_the_close_button_shows_on_linux(qtbot):
    explorer = panel(qtbot)
    explorer.show()

    assert explorer.close_button.isVisible()


def test_macos_has_no_close_button(qtbot):
    explorer = panel(qtbot, platform="darwin")
    explorer.show()

    assert not explorer.close_button.isVisible()


def deck_actions(explorer):
    menu = explorer.deck_selector.menu()
    menu.aboutToShow.emit()
    return [action for action in menu.actions() if not action.isSeparator()]


def test_preferred_width_follows_the_selected_deck(qtbot):
    explorer = panel(qtbot)
    if len(deck_actions(explorer)) < 2:
        return

    widths = []
    for action in deck_actions(explorer):
        action.trigger()
        widths.append((explorer.preferred_width(), widest_row(explorer)))

    for preferred, widest in widths:
        assert preferred >= widest


def first_group_and_card(explorer):
    model = explorer.model
    group = model.index(0, 0)
    return group, model.index(0, 0, group)


def test_card_rows_drag_and_group_rows_do_not(qtbot):
    explorer = panel(qtbot)
    group, card = first_group_and_card(explorer)

    assert explorer.model.flags(card) & Qt.ItemFlag.ItemIsDragEnabled
    assert not explorer.model.flags(group) & Qt.ItemFlag.ItemIsDragEnabled
    assert explorer.tree_view.dragDropMode() == QAbstractItemView.DragDropMode.DragOnly


def test_a_dragged_row_carries_its_card_and_deck(qtbot):
    explorer = panel(qtbot)
    _, index = first_group_and_card(explorer)
    row = index.data(Qt.ItemDataRole.UserRole)

    mime = explorer.model.mimeData([index])

    card, deck, is_reversed = card_from_mime(mime, [row["deck"]])
    assert card.canonical_id == row["card"].canonical_id
    assert deck is row["deck"]
    assert not is_reversed
    assert explorer.model.mimeTypes() == [CARD_MIME]


def test_the_drag_shows_the_card_art(qtbot):
    explorer = panel(qtbot)
    _, index = first_group_and_card(explorer)

    pixmap = explorer.tree_view.drag_pixmap(index.data(Qt.ItemDataRole.UserRole)["card"])

    assert pixmap is not None
    assert pixmap.deviceIndependentSize().height() == explorer.tree_view.DRAG_HEIGHT


def test_a_card_row_offers_open_and_copy(qtbot, clipboard):
    explorer = panel(qtbot)
    group, index = first_group_and_card(explorer)
    row = index.data(Qt.ItemDataRole.UserRole)

    assert explorer.card_menu(group) is None
    menu = explorer.card_menu(index)
    actions = {action.text().replace("&", ""): action for action in menu.actions()}
    assert list(actions) == ["Open Card", "Copy Card"]

    actions["Copy Card"].trigger()
    assert (
        card_from_mime(clipboard.mimeData(), [row["deck"]])[0].canonical_id
        == row["card"].canonical_id
    )

    with qtbot.waitSignal(explorer.card_action_requested) as opened:
        actions["Open Card"].trigger()
    assert opened.args[0] == "view_card"
    assert opened.args[1].canonical_id == row["card"].canonical_id


def test_decks_changed_repopulates_the_deck_selector(
    qtbot, tmp_path, stub_deck_library, minimal_deck
):
    import shutil

    from tarot_canvas.models.arcana_backend import load_deck
    from tarot_canvas.models.deck_events import deck_events
    from tests.conftest import MINIMAL_DECK_PATH

    explorer = panel(qtbot)
    assert len(deck_actions(explorer)) == 1

    shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "second")
    manifest = tmp_path / "second" / "deck.toml"
    manifest.write_text(manifest.read_text().replace("Minimal Test Deck", "Second Deck"))
    second = load_deck(str(tmp_path / "second"))
    stub_deck_library.decks = lambda: [minimal_deck, second]
    deck_events().decks_changed.emit()

    assert [action.text() for action in deck_actions(explorer)] == [
        "Minimal Test Deck",
        "Second Deck",
    ]
    assert explorer.deck_selector.title() == "Minimal Test Deck"

    deck_actions(explorer)[1].trigger()
    assert explorer.current_deck is second
    assert explorer.deck_selector.title() == "Second Deck"


def test_decks_changed_keeps_the_deck_by_folder_and_what_is_collapsed(
    qtbot, stub_deck_library, other_deck
):
    from tarot_canvas.models.deck_events import deck_events

    explorer = panel(qtbot)
    explorer.choose_deck(other_deck)  # named as the first is
    explorer.tree_view.collapse(explorer.model.index(0, 0))

    deck_events().decks_changed.emit()

    assert explorer.current_deck is other_deck
    assert [action.isChecked() for action in deck_actions(explorer)].count(True) == 1
    assert not explorer.tree_view.isExpanded(explorer.model.index(0, 0))


def test_a_reloaded_deck_rebuilds_the_tree(qtbot, stub_deck_library, other_deck, minimal_deck):
    from tarot_canvas.models.arcana_backend import load_deck
    from tarot_canvas.models.deck_events import deck_events

    explorer = panel(qtbot)
    explorer.choose_deck(other_deck)
    reloaded = load_deck(str(other_deck.root_path))
    stub_deck_library.decks = lambda: [minimal_deck, reloaded]

    deck_events().decks_changed.emit()

    assert explorer.current_deck is reloaded
    assert explorer.model.index(0, 0).data(Qt.ItemDataRole.UserRole)["deck"] is reloaded


def test_the_chosen_deck_going_leaves_the_first_and_none_leaves_nothing(
    qtbot, stub_deck_library, other_deck, minimal_deck
):
    from tarot_canvas.models.deck_events import deck_events

    explorer = panel(qtbot)
    explorer.choose_deck(other_deck)

    stub_deck_library.decks = lambda: [minimal_deck]
    deck_events().decks_changed.emit()
    assert explorer.current_deck is minimal_deck

    stub_deck_library.decks = lambda: []
    deck_events().decks_changed.emit()
    assert explorer.current_deck is None
    assert explorer.model.rowCount() == 0
