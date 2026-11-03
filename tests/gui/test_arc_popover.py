import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialogButtonBox

from tarot_canvas.ui.canvas.arc_popover import ARC_DEFAULTS, clock
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def add_cards(tab, count, apart=40):
    """`count` selected 100-wide cards in a row, `apart` pixels between them"""
    pixmap = QPixmap(100, 160)
    pixmap.fill()
    cards = []
    for i in range(count):
        card = DraggableCardItem(pixmap, {"id": f"card-{i}"}, tab)
        card.setPos(i * (100 + apart), 0)
        tab.scene.addItem(card)
        card.setZValue(i)
        card.setSelected(True)
        cards.append(card)
    return cards


def places(cards):
    return [(QPointF(card.pos()), card.orient) for card in cards]


def count_layout_changes(tab):
    changes = []
    tab.layout_changed.connect(lambda: changes.append(1))
    return changes


@pytest.fixture
def tab(qtbot):
    tab = make_tab(qtbot)
    yield tab
    if tab.arc_popover is not None:
        tab.arc_popover.close()
    qtbot.wait(1100)


def test_opening_previews_the_arc(tab):
    cards = add_cards(tab, 4)
    before = places(cards)
    tab.open_arc_popover()
    assert places(cards) != before


def test_moving_the_sweep_moves_the_cards(tab):
    cards = add_cards(tab, 4)
    popover = tab.open_arc_popover()
    full = places(cards)
    popover.sweep.setValue(6)  # 90 degrees
    assert places(cards) != full


def test_the_preview_never_drifts(tab):
    cards = add_cards(tab, 5)
    popover = tab.open_arc_popover()
    first = places(cards)
    popover.sweep.setValue(4)
    popover.follow.setChecked(True)
    popover.sweep.setValue(24)
    popover.upright.setChecked(True)
    assert places(cards) == first


def test_cancel_puts_every_card_back(tab):
    cards = add_cards(tab, 4)
    cards[1].set_orient(30)
    before = places(cards)
    changes = count_layout_changes(tab)

    popover = tab.open_arc_popover()
    popover.follow.setChecked(True)
    popover.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()

    assert not popover.isVisible()
    assert places(cards) == before
    assert changes == []


def test_esc_puts_every_card_back(tab, qtbot):
    cards = add_cards(tab, 4)
    before = places(cards)
    changes = count_layout_changes(tab)

    popover = tab.open_arc_popover()
    popover.sweep.setValue(10)
    qtbot.keyClick(popover.sweep, Qt.Key.Key_Escape)

    assert not popover.isVisible()
    assert places(cards) == before
    assert changes == []


def test_closing_from_outside_puts_every_card_back(tab):
    cards = add_cards(tab, 4)
    before = places(cards)
    popover = tab.open_arc_popover()
    popover.close()  # what a click outside a Popup does
    assert places(cards) == before


def test_apply_keeps_the_arc_and_changes_the_layout_once(tab):
    cards = add_cards(tab, 4)
    changes = count_layout_changes(tab)
    popover = tab.open_arc_popover()
    popover.sweep.setValue(12)
    arranged = places(cards)

    popover.buttons.button(QDialogButtonBox.StandardButton.Apply).click()

    assert not popover.isVisible()
    assert places(cards) == arranged
    assert changes == [1]


def test_the_first_arc_starts_from_the_defaults(tab):
    add_cards(tab, 3)
    assert tab.open_arc_popover().settings() == ARC_DEFAULTS


def test_reopening_keeps_the_last_choices_and_measures_the_spacing_again(tab):
    cards = add_cards(tab, 3, apart=40)
    popover = tab.open_arc_popover()
    assert popover.gap() == pytest.approx(0.4, abs=0.015)  # a smooth pixmap is 1px wider
    popover.sweep.setValue(12)
    popover.start.setValue(18)
    popover.anticlockwise.setChecked(True)
    popover.follow.setChecked(True)
    popover.spacing.setValue(90)
    popover.close()

    for i, card in enumerate(cards):
        card.setPos(i * 120, 0)
    again = tab.open_arc_popover()
    assert again.settings() == {"sweep": 180, "start": 270, "clockwise": False, "follow": True}
    assert again.gap() == pytest.approx(0.2, abs=0.015)


def test_a_wide_spacing_is_clamped_to_one_width(tab):
    add_cards(tab, 3, apart=500)
    assert tab.open_arc_popover().gap() == 1.0


@pytest.mark.parametrize(
    "degrees,hour,minute", [(0, 12, 0), (15, 12, 30), (90, 3, 0), (105, 3, 30), (345, 11, 30)]
)
def test_start_reads_as_a_clock(degrees, hour, minute):
    assert clock(degrees) == (hour, minute)


def test_choosing_the_arc_from_the_menu_changes_nothing_yet(tab, monkeypatch):
    add_cards(tab, 3)
    changes = count_layout_changes(tab)

    def choose_arc(menu, *_):
        arc = menu.actions()[-1]
        menu.triggered.emit(arc)
        return arc

    monkeypatch.setattr("tarot_canvas.ui.tabs.canvas_tab.QMenu.exec", choose_arc)
    tab.on_align_cards()

    assert tab.arc_popover is not None and tab.arc_popover.isVisible()
    assert changes == []
