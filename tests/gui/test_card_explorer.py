from PyQt6.QtGui import QFontMetrics

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
