from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QAbstractItemView

from tarot_canvas.ui.card_transfer import CARD_MIME, card_from_mime
from tarot_canvas.ui.components.card_explorer import CardExplorerPanel


def panel(qtbot):
    widget = CardExplorerPanel()
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


def test_preferred_width_follows_the_selected_deck(qtbot):
    explorer = panel(qtbot)
    if explorer.deck_selector.count() < 2:
        return

    widths = []
    for i in range(explorer.deck_selector.count()):
        explorer.deck_selector.setCurrentIndex(i)
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
    assert card["id"] == row["card"]["id"]
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
    assert card_from_mime(clipboard.mimeData(), [row["deck"]])[0]["id"] == row["card"]["id"]

    with qtbot.waitSignal(explorer.card_action_requested) as opened:
        actions["Open Card"].trigger()
    assert opened.args[0] == "view_card"
    assert opened.args[1]["id"] == row["card"]["id"]
