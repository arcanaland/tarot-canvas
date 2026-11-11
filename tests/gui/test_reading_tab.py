import logging
import random
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QHelpEvent, QKeyEvent, QMouseEvent, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from tarot_canvas.models import spreads
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.spreads import BUNDLED_SPREADS_PATH, Position, Spread
from tarot_canvas.settings import (
    MOTION_LEVEL_KEY,
    get_readings_deck,
    get_readings_reversals,
    get_settings,
    set_readings_deck,
)
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas import placement as placement_module
from tarot_canvas.ui.canvas import reading_strip as strip_module
from tarot_canvas.ui.canvas.candle import CANDLE_ALPHA, dim_tone
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.halo import STEADY as HALO_STEADY
from tarot_canvas.ui.canvas.halo import HaloItem
from tarot_canvas.ui.canvas.placement import (
    FACE_DOWN_GROUND_PACE,
    Phase,
    SocketItem,
    socket_fill,
)
from tarot_canvas.ui.canvas.reading_card import FACE_DOWN_MARK, ReadingCard
from tarot_canvas.ui.canvas.reading_strip import DEAL_ICON, FINISH_ICON, ProgressDots
from tarot_canvas.ui.card_colours import card_colour
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import COMMANDS, READINGS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.reading_tab import CARD_Z, NEXT_Z, ReadingTab
from tests.conftest import write_full_deck

LEFT = Qt.MouseButton.LeftButton
NONE = Qt.MouseButton.NoButton
LEVELS = ("Off", "Reactive", "Full")


def celtic_cross():
    return spreads.load(BUNDLED_SPREADS_PATH / "celtic-cross")


def three_card():
    return spreads.load(BUNDLED_SPREADS_PATH / "three-card")


def many_positions(count):
    return Spread(
        name="Many",
        positions=tuple(
            Position(id=f"p{n}", label=f"Place {n}", meaning="", x=(n % 10) * 1.2, y=n // 10 * 1.8)
            for n in range(1, count + 1)
        ),
    )


def write_deck(root, count):
    """A deck of the first count cards that have art"""
    write_full_deck(root)
    pngs = sorted(root.rglob("*.png"))
    for png in pngs[count:]:
        png.unlink()
    return TarotDeck(str(root))


@pytest.fixture
def deck(tmp_path, stub_deck_manager, qapp):
    full = TarotDeck(str(write_full_deck(tmp_path / "full")))
    stub_deck_manager.get_reference_deck = lambda: full
    stub_deck_manager.get_all_decks = lambda: [full]
    return full


@pytest.fixture
def short_deck(tmp_path, stub_deck_manager, qapp):
    small = write_deck(tmp_path / "short", 3)
    stub_deck_manager.get_reference_deck = lambda: small
    stub_deck_manager.get_all_decks = lambda: [small]
    return small


def at_level(level):
    get_settings().setValue(MOTION_LEVEL_KEY, level)


@pytest.fixture
def off():
    at_level("Off")


def make_tab(qtbot, spread=None):
    tab = ReadingTab(spread or celtic_cross())
    qtbot.addWidget(tab)
    tab.resize(1200, 800)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def deal(qtbot, tab):
    tab.deal()
    qtbot.waitUntil(lambda: not tab.is_dealing(), timeout=5000)


def read(qtbot, tab):
    tab.turn_all()
    qtbot.waitUntil(lambda: tab.phase is Phase.READ, timeout=10000)


def centre_on_screen(tab, item):
    return tab.view.mapFromScene(item.sceneBoundingRect().center())


def send_mouse(tab, kind, pos, button=LEFT, buttons=None, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = tab.view.viewport()
    pos = QPointF(pos)
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            kind,
            pos,
            QPointF(viewport.mapToGlobal(pos.toPoint())),
            button,
            button if buttons is None else buttons,
            modifiers,
        ),
    )


def click(tab, item):
    pos = centre_on_screen(tab, item)
    send_mouse(tab, QEvent.Type.MouseButtonPress, pos)
    send_mouse(tab, QEvent.Type.MouseButtonRelease, pos, buttons=NONE)


def press_key(widget, key, modifiers=Qt.KeyboardModifier.NoModifier, repeat=False, text=""):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text, repeat))


def number_of(tab, card):
    return tab.placement_of(card).number


# -- staged


def test_the_celtic_cross_opens_staged_with_ten_sockets_listed(qtbot, deck):
    tab = make_tab(qtbot)

    sockets = tab.slots()
    assert tab.phase is Phase.STAGED
    assert len(sockets) == 10
    assert all(isinstance(slot, SocketItem) and slot.isVisible() for slot in sockets)
    assert not any(slot.shadow.isVisible() for slot in sockets)
    assert tab.positions.rowCount() == 10
    assert [tab.positions.index(row).data() for row in range(2)] == [
        sockets[0].label,
        sockets[1].label,
    ]
    assert not tab.cards()[0].flags() & DraggableCardItem.GraphicsItemFlag.ItemIsSelectable


def test_a_crossing_sockets_text_is_turned_back_upright(qtbot, deck, monkeypatch):
    turns = {}
    render = placement_module.render_slot

    def spy(number, *args, **kwargs):
        turns[number] = kwargs["text_turn"]
        return render(number, *args, **kwargs)

    monkeypatch.setattr(placement_module, "render_slot", spy)
    tab = make_tab(qtbot)
    for slot in tab.slots():
        slot.redraw()

    assert tab.slots()[1].orient == 90
    assert turns[2] == 90
    assert {turn for number, turn in turns.items() if number != 2} == {0}


def test_a_socket_is_opaque_plum_over_the_ground_and_follows_it(qtbot, deck):
    tab = make_tab(qtbot)
    slot = tab.slots()[0]
    before = slot.pixmap().toImage()

    fill = socket_fill("#ffffff")
    tab.set_ground(placement_module.QColor("#ffffff"))

    assert fill.alpha() == 255
    assert fill != placement_module.SOCKET_PLUM
    assert slot.pixmap().toImage() != before


def test_the_pane_offers_the_deck_and_reversals_until_the_deal(qtbot, deck, off):
    tab = make_tab(qtbot)
    pane = tab.pane

    assert not pane.deck_combo.isHidden()
    assert not pane.reversals_check.isHidden()
    assert pane.date_text.isHidden()
    assert pane.deck_combo.currentData() is deck

    deal(qtbot, tab)

    assert pane.deck_combo.isHidden()
    assert pane.deck_label.text() == deck.get_name()
    assert pane.reversals_check.isHidden()
    assert pane.reversals_label.text() == READINGS["reversals_with"]
    assert not pane.date_text.isHidden()
    assert pane.date_text.text()


def test_reversals_is_the_users_last_choice(qtbot, deck, off):
    assert get_readings_reversals() is True
    first = make_tab(qtbot)
    first.pane.reversals_check.setChecked(False)

    assert get_readings_reversals() is False
    second = make_tab(qtbot)
    assert not second.pane.reversals_check.isChecked()


# -- the deal


@pytest.mark.parametrize("level", LEVELS)
def test_the_deal_lays_the_celtic_cross_face_down(qtbot, deck, level):
    at_level(level)
    tab = make_tab(qtbot)

    deal(qtbot, tab)

    cards = [placement.card for placement in tab.placements]
    assert all(isinstance(card, ReadingCard) and card.face_down for card in cards)
    assert all(tab.has_landed(card) for card in cards)
    assert [card.orient for card in cards[:2]] == [0.0, 90.0]
    for placement in tab.placements:
        centre = placement.card.pos() + placement.card.boundingRect().center()
        assert (centre - placement.slot.sceneBoundingRect().center()).manhattanLength() < 1
        assert not placement.slot.isVisible()
        assert not placement.slot.shadow.isVisible()
    assert tab.phase is Phase.DEALT
    assert tab.next_card() is cards[0]
    assert cards[0].zValue() == NEXT_Z
    assert len({card.card_data["id"] for card in cards}) == 10


def test_the_ground_slows_while_face_down_and_comes_back_once_read(qtbot, deck, off, monkeypatch):
    tab = make_tab(qtbot, three_card())
    assert tab.ground_pace.value == 1.0
    deal(qtbot, tab)
    assert tab.ground_pace.target == FACE_DOWN_GROUND_PACE
    monkeypatch.setattr(tab, "ground_motion_is_allowed", lambda: True)
    tab._advance_motion(0.0, 0.3)
    assert FACE_DOWN_GROUND_PACE < tab.ground_pace.value < 1.0
    read(qtbot, tab)
    assert tab.ground_pace.target == 1.0


def test_held_still_the_ground_snaps_to_its_pace(qtbot, deck, off, monkeypatch):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    monkeypatch.setattr(tab, "ground_motion_is_allowed", lambda: False)
    tab._advance_motion(0.0, 0.016)
    assert tab.ground_pace.value == FACE_DOWN_GROUND_PACE


def test_an_ordinary_canvas_keeps_its_ground_at_full_pace(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab._advance_motion(0.0, 1.0)
    assert tab.ground_pace.value == tab.ground_pace.target == 1.0


def test_a_filled_socket_is_left_out_of_the_cards(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    assert not any(isinstance(card, SocketItem) for card in tab.cards())


def test_summon_deals_while_staged(qtbot, deck, off):
    tab = make_tab(qtbot)

    tab.commands["canvas.summon"].trigger()

    assert tab.phase is Phase.DEALT


def test_a_double_click_on_the_empty_canvas_deals_while_staged(qtbot, deck, off):
    tab = make_tab(qtbot)

    send_mouse(tab, QEvent.Type.MouseButtonDblClick, QPoint(5, 5))

    assert tab.phase is Phase.DEALT


def test_a_short_deal_deals_what_there_is_and_says_so(qtbot, short_deck, off, monkeypatch):
    toasts = []
    monkeypatch.setattr(ReadingTab, "_toast", lambda self, text: toasts.append(text))
    tab = make_tab(qtbot)

    deal(qtbot, tab)

    filled = [placement for placement in tab.placements if placement.card is not None]
    assert [placement.number for placement in filled] == [1, 2, 3]
    assert sum(slot.isVisible() for slot in tab.slots()) == 7
    assert toasts == [READINGS["short_deal"].format(dealt=3, positions=10)]
    assert len(tab.turn_order()) == 3


def test_a_seventy_nine_position_spread_deals_the_whole_deck(qtbot, deck, off):
    tab = make_tab(qtbot, many_positions(79))

    deal(qtbot, tab)

    assert sum(placement.card is not None for placement in tab.placements) == 78
    assert tab.placements[-1].card is None
    assert tab.slots()[-1].isVisible()
    read(qtbot, tab)
    assert tab.phase is Phase.READ


def test_a_card_with_no_face_is_left_out_of_the_draw(qtbot, deck, off, monkeypatch):
    cards = list(deck.get_all_cards())
    faceless = {**cards[0], "id": "faceless", "image": "/nowhere.png"}
    monkeypatch.setattr(deck, "get_all_cards", lambda: [faceless, *cards[1:10]])
    tab = make_tab(qtbot)

    deal(qtbot, tab)

    assert "faceless" not in {card.card_data["id"] for card in tab.turn_order()}
    assert len(tab.turn_order()) == 9


def test_a_card_staged_on_a_socket_fills_it_by_hand(qtbot, deck, off):
    tab = make_tab(qtbot)
    first = tab.slots()[0]
    staged = tab.add_specific_card(
        deck.get_all_cards()[0], deck, False, first.sceneBoundingRect().center()
    )
    staged.setPos(staged.pos() + QPointF(3, 3))

    assert tab.card_in(first) is staged
    deal(qtbot, tab)

    placement = tab.placements[0]
    assert placement.card is staged and placement.by_hand
    assert not first.isVisible()
    centre = staged.pos() + staged.boundingRect().center()
    assert (centre - first.sceneBoundingRect().center()).manhattanLength() < 1
    dealt = [card for card in tab.turn_order() if card is not staged]
    assert staged.card_data["id"] not in {card.card_data["id"] for card in dealt}
    assert tab.turn_order()[0] is staged
    assert number_of(tab, tab.next_card()) == 2


def test_reversals_off_deals_every_card_upright(qtbot, deck, off, monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)
    tab = make_tab(qtbot)
    tab.pane.reversals_check.setChecked(False)

    deal(qtbot, tab)
    read(qtbot, tab)

    assert not any(card.is_reversed() for card in tab.turn_order())
    assert tab.pane.reversals_label.text() == READINGS["reversals_without"]


# -- what a face-down card gives away: nothing


@pytest.fixture
def all_reversed(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: 0.0)


def test_a_reversed_cards_back_lies_upright(qtbot, deck, off, all_reversed):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    card = tab.next_card()
    assert card.drawn_reversed
    assert not card.reversed
    assert card.motion.drawn_angle() == card.orient


def test_a_face_down_card_shows_no_suit_on_the_tab_icon(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    card = tab.next_card()
    assert card.mark_colour() == FACE_DOWN_MARK
    assert card.mark_colour() != card_colour(card.card_data)


def test_zooming_in_loads_no_face_while_face_down(qtbot, deck, off, monkeypatch):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    card = tab.next_card()
    back = card.pixmap().cacheKey()

    def no_loading():
        raise AssertionError("a face-down card asked for its art")

    monkeypatch.setattr("tarot_canvas.ui.canvas.card_item.art_loader", no_loading)
    card._top_level = 4
    card.set_detail(4.0)

    assert card.pixmap().cacheKey() == back


def test_double_clicking_a_face_down_card_opens_nothing(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    opened = []
    tab.navigation_requested.connect(lambda *args: opened.append(args))
    second = tab.placements[4].card

    pos = centre_on_screen(tab, second)
    for kind, buttons in (
        (QEvent.Type.MouseButtonPress, LEFT),
        (QEvent.Type.MouseButtonRelease, NONE),
        (QEvent.Type.MouseButtonDblClick, LEFT),
        (QEvent.Type.MouseButtonRelease, NONE),
    ):
        send_mouse(tab, kind, pos, buttons=buttons)

    assert opened == []
    assert second.face_down


def test_a_face_down_card_has_no_menu(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    card = tab.placements[3].card

    assert tab.card_menu(card.sceneBoundingRect().center()) is None
    assert tab.build_card_menu(card) is None


def test_a_slot_has_no_menu(qtbot, deck, off):
    tab = make_tab(qtbot)
    slot = tab._slots[0]
    assert tab.card_menu(slot.sceneBoundingRect().center()) is None


def test_the_empty_ground_offers_the_readings_own_background(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    menu = tab.card_menu(QPointF(9000, 9000))

    (action,) = menu.actions()
    assert action.text() == commands.by_id("window.canvas_background").text
    action.trigger()
    assert tab.background_is_open()
    tab.background_panel.cancel()


def test_ctrl_wheel_does_not_turn_a_face_down_card(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    card = tab.placements[3].card
    viewport = tab.view.viewport()
    pos = centre_on_screen(tab, card)

    QApplication.sendEvent(
        viewport,
        QWheelEvent(
            QPointF(pos),
            QPointF(viewport.mapToGlobal(pos)),
            QPoint(),
            QPoint(0, 120),
            NONE,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )

    assert card.orient == 0.0


def test_the_deal_names_no_card_above_debug(qtbot, deck, off, caplog):
    tab = make_tab(qtbot)
    names = {card["name"] for card in deck.get_all_cards()}

    with caplog.at_level(logging.DEBUG):
        deal(qtbot, tab)

    loud = [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG]
    assert not any(name in message for message in loud for name in names)
    quiet = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(tab.turn_order()[0].card_data["name"] in message for message in quiet)


# -- the turn


@pytest.mark.parametrize("level", LEVELS)
def test_clicking_the_next_card_turns_it_and_only_it(qtbot, deck, level, all_reversed):
    at_level(level)
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    first, second = tab.placements[0].card, tab.placements[1].card

    click(tab, tab.placements[4].card)
    assert tab.placements[4].card.face_down
    click(tab, first)
    qtbot.waitUntil(lambda: not first.is_turning(), timeout=5000)

    assert not first.face_down
    assert first.reversed
    assert first.zValue() == CARD_Z + tab.placements[0].slot.zValue()
    assert second.face_down
    assert tab.next_card() is second
    assert second.zValue() == NEXT_Z


def test_the_face_shows_only_at_the_turn(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    second = tab.placements[1].card
    back = second.pixmap().cacheKey()

    tab.turn_next()
    assert second.pixmap().cacheKey() == back
    tab.turn_next()
    assert second.pixmap().cacheKey() == second.face_pixmap().cacheKey()


@pytest.mark.parametrize("level", LEVELS)
def test_reveal_all_turns_the_rest_in_number_order(qtbot, deck, level):
    at_level(level)
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    turned = []
    real = tab.card_turned
    tab.card_turned = lambda card: (turned.append(number_of(tab, card)), real(card))

    tab.turn_next()
    read(qtbot, tab)

    assert turned == list(range(1, 11))
    assert not any(card.face_down for card in tab.turn_order())


def test_hiding_the_tab_mid_deal_lands_every_card(qtbot, deck):
    at_level("Full")
    tab = make_tab(qtbot)
    tab.deal()
    assert tab.is_dealing()

    tab.hide()

    assert not tab.is_dealing()
    assert all(tab.has_landed(card) for card in tab.turn_order())
    assert tab.next_card() is tab.placements[0].card


# -- keys


def test_space_deals_then_turns_on_the_canvas(qtbot, deck, off):
    tab = make_tab(qtbot)

    press_key(tab.view, Qt.Key.Key_Space, text=" ")
    assert tab.phase is Phase.DEALT
    press_key(tab.view, Qt.Key.Key_Return)
    press_key(tab.view, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)

    assert [card.face_down for card in tab.turn_order()[:3]] == [False, False, True]


def test_a_held_or_modified_key_turns_nothing(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    press_key(tab.view, Qt.Key.Key_Space, repeat=True)
    press_key(tab.view, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)

    assert all(card.face_down for card in tab.turn_order())


def test_right_turns_and_end_reveals_all_on_the_canvas(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    press_key(tab.view, Qt.Key.Key_Right)
    assert not tab.turn_order()[0].face_down
    assert tab.turn_order()[1].face_down
    press_key(tab.view, Qt.Key.Key_End)

    assert tab.phase is Phase.READ


def test_once_read_the_arrows_step_through_the_positions(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    read(qtbot, tab)
    order = tab.turn_order()

    press_key(tab.view, Qt.Key.Key_Right)
    assert tab.stepped_card() is order[0]
    press_key(tab.view, Qt.Key.Key_Right)
    assert tab.stepped_card() is order[1]
    press_key(tab.view, Qt.Key.Key_End)
    assert tab.stepped_card() is order[-1]
    press_key(tab.view, Qt.Key.Key_Left)
    assert tab.stepped_card() is order[-2]
    press_key(tab.view, Qt.Key.Key_Home)
    assert tab.stepped_card() is order[0]
    assert tab.pane.list_view.currentIndex().row() == 0


def test_a_space_typed_in_the_question_stays_a_space(qtbot, deck, off):
    tab = make_tab(qtbot)
    question = tab.pane.question_edit
    question.setFocus()

    QTest.keyClicks(question, "Will it rain")

    assert question.toPlainText() == "Will it rain"
    assert tab.phase is Phase.STAGED


def test_enter_in_the_question_deals_and_gives_the_canvas_the_keys(qtbot, deck, off):
    tab = make_tab(qtbot)
    QTest.keyClick(tab.pane.question_edit, Qt.Key.Key_Return)

    assert tab.phase is Phase.DEALT
    assert tab.pane.question_edit.toPlainText() == ""


def test_space_on_the_list_turns_and_enter_on_a_turned_row_opens_its_card(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    rows = tab.pane.list_view
    opened = []
    tab.navigation_requested.connect(lambda kind, data: opened.append(data["card"]["id"]))

    press_key(rows, Qt.Key.Key_Space, text=" ")
    rows.setCurrentIndex(tab.positions.index(0))
    press_key(rows, Qt.Key.Key_Return)

    assert opened == [tab.placements[0].card.card_data["id"]]
    assert tab.placements[1].card.face_down


# -- the strip and the bar


def test_the_rail_is_hidden_until_read_and_view_lives_in_the_strip(qtbot, deck, off):
    tab = make_tab(qtbot)
    view_actions = [*tab.view_actions, tab.pane_action]

    assert tab.toolbar.isHidden()
    assert [button.defaultAction() for button in tab.strip.buttons] == view_actions
    assert not set(view_actions) & set(tab.toolbar.actions())
    # The keys stay the tab's while the rail is gone
    assert tab.commands["canvas.summon"] in tab.actions()
    deal(qtbot, tab)
    assert tab.toolbar.isHidden()
    read(qtbot, tab)

    assert not tab.toolbar.isHidden()
    assert tab.commands["canvas.summon"] in tab.toolbar.actions()


def test_the_bar_deals_then_turns_then_steps(qtbot, deck, off):
    tab = make_tab(qtbot)
    bar = tab.bar

    def shown():
        names = ("deal", "previous", "turn", "dots", "reveal", "next")
        return [name for name in names if not getattr(bar, name).isHidden()]

    assert shown() == ["deal"]
    QTest.mouseClick(bar.deal, LEFT)
    assert shown() == ["turn", "dots", "reveal"]
    assert bar.turn.toolTip().startswith(READINGS["turn_next"])
    assert bar.reveal.toolTip().startswith(READINGS["turn_all"])
    QTest.mouseClick(bar.turn, LEFT)
    assert not tab.turn_order()[0].face_down
    QTest.mouseClick(bar.reveal, LEFT)

    assert shown() == ["previous", "dots", "next"]
    assert bar.previous.toolTip().startswith(COMMANDS["go_previous"].replace("&", ""))
    assert bar.next.toolTip().startswith(COMMANDS["go_next"].replace("&", ""))
    QTest.mouseClick(bar.next, LEFT)
    assert tab.stepped_card() is tab.turn_order()[0]
    assert not bar.previous.isEnabled()


def test_the_dots_mark_the_next_card_in_gilt_and_turned_ones_filled(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    tab.turn_next()
    dots = tab.bar.dots
    turned, following, waiting = tab.turn_order()[:3]

    gilt = dots.colours(following)
    assert gilt[0] == gilt[1]
    assert dots.colours(turned) == (dots.palette().windowText().color(), None)
    assert dots.colours(waiting)[0] is None
    assert dots.toolTip() == ""


def test_too_many_dots_for_the_bar_fold_into_a_line(qtbot, deck, off):
    tab = make_tab(qtbot, many_positions(79))
    deal(qtbot, tab)
    qtbot.waitUntil(lambda: tab.bar.dots.width() > 0)

    assert tab.bar.dots.as_line()
    assert tab.bar.width() <= tab.view.width()


def test_a_hover_sweep_over_the_bar_dots_and_rows_raises_nothing(qtbot, deck, off):
    """Every overridden event and helpEvent, sent the real thing"""
    for spread in (many_positions(79), celtic_cross()):
        tab = make_tab(qtbot, spread)
        deal(qtbot, tab)
        tab.turn_next()
        rows = tab.pane.list_view
        rows.setCurrentIndex(tab.positions.index(0))
        targets = [tab.bar, tab.bar.dots, tab.bar.turn, tab.bar.reveal, rows.viewport()]
        for widget in targets:
            for x in range(0, widget.width(), 7):
                for y in range(0, widget.height(), 7):
                    point = QPoint(x, y)
                    QApplication.sendEvent(
                        widget,
                        QHelpEvent(QEvent.Type.ToolTip, point, widget.mapToGlobal(point)),
                    )
                    QApplication.sendEvent(
                        widget,
                        QMouseEvent(
                            QEvent.Type.MouseMove,
                            QPointF(point),
                            QPointF(widget.mapToGlobal(point)),
                            NONE,
                            NONE,
                            Qt.KeyboardModifier.NoModifier,
                        ),
                    )
        read(qtbot, tab)
        assert isinstance(tab.bar.dots, ProgressDots)


# -- badges and the caption


def test_badges_mark_each_landed_card_and_light_the_next(qtbot, deck, off):
    tab = make_tab(qtbot)
    assert tab._badge_marks() == []

    deal(qtbot, tab)

    marks = tab._badge_marks()
    assert [number for _card, number, _lit in marks] == list(range(1, 11))
    assert [lit for _card, _number, lit in marks] == [True] + [False] * 9
    tab.view.viewport().grab()


def test_the_caption_names_the_next_position_and_goes_once_read(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    assert tab.caption.slot is tab.slots()[0]
    rect = tab.caption.rect()
    assert rect.left() >= 0 and rect.right() <= tab.view.viewport().width()
    tab.view.viewport().grab()
    read(qtbot, tab)
    assert tab.caption.slot is None


def test_the_caption_goes_above_a_card_with_no_room_below(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    slot = tab.slots()[0]
    view = tab.view
    # The next card's position at the view's foot
    view.centerOn(slot.sceneBoundingRect().center() - QPointF(0, view.viewport().height() / 2 - 20))

    top = view.mapFromScene(slot.sceneBoundingRect()).boundingRect().top()
    assert tab.caption.rect().bottom() <= top


# -- read


def test_ambient_motion_waits_until_the_reading_is_read(qtbot, deck, off, monkeypatch):
    monkeypatch.setattr(CanvasTab, "ambient_is_allowed", lambda self: True)
    tab = make_tab(qtbot)
    assert not tab.ambient_is_allowed()
    deal(qtbot, tab)
    assert not tab.ambient_is_allowed()
    read(qtbot, tab)

    assert tab.ambient_is_allowed()


def test_only_extra_cards_can_be_deleted(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    read(qtbot, tab)
    dealt = tab.turn_order()

    tab.on_draw_card(QPointF(2000, 2000))
    extra = [card for card in tab.cards() if card not in dealt and not isinstance(card, SocketItem)]
    assert len(extra) == 1
    assert extra[0].deck is deck
    assert extra[0].card_data["id"] not in {card.card_data["id"] for card in dealt}

    tab.scene.clearSelection()
    dealt[0].setSelected(True)
    assert not tab.can_delete()
    assert not tab.commands["canvas.delete"].isEnabled()
    tab.on_delete_card()
    assert dealt[0].scene() is tab.scene

    tab.select_all()
    assert tab.can_delete()
    tab.delete()
    assert extra[0].scene() is None
    assert all(card.scene() is tab.scene for card in dealt)


def test_summon_after_a_whole_deck_is_dealt_adds_nothing(qtbot, short_deck, off):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    read(qtbot, tab)
    before = tab.cards()

    tab.on_draw_card()

    assert tab.cards() == before


def test_swapping_a_cards_deck_moves_its_position(qtbot, deck, off, tmp_path, stub_deck_manager):
    other = TarotDeck(str(write_full_deck(tmp_path / "other", name="Other")))
    stub_deck_manager.get_all_decks = lambda: [deck, other]
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    read(qtbot, tab)
    old = tab.placements[2].card
    card = other.get_card_by_id(old.card_data["id"])

    replacement = tab.swap_card(old, other, card)

    assert tab.placements[2].card is replacement
    assert tab.turn_order()[2] is replacement
    assert tab.card_in(tab.slots()[2]) is replacement


# -- rows and cards


def test_a_turned_card_and_its_row_select_each_other(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    rows = tab.pane.list_view

    rows.setCurrentIndex(tab.positions.index(4))
    assert tab.selected_cards() == []
    tab.turn_all()
    QTest.mouseClick(rows.viewport(), LEFT, pos=rows.visualRect(tab.positions.index(4)).center())
    assert tab.selected_cards() == [tab.placements[4].card]
    rows.setCurrentIndex(tab.positions.index(5))
    assert tab.selected_cards() == [tab.placements[5].card]

    tab.scene.clearSelection()
    tab.placements[6].card.setSelected(True)
    assert [index.row() for index in rows.selectionModel().selectedRows()] == [6]


def test_the_selected_and_the_next_rows_open(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    rows = tab.pane.rows

    assert rows.is_open(tab.positions.index(0))
    tab.turn_next()
    tab.pane.list_view.setCurrentIndex(tab.positions.index(5))

    assert [rows.is_open(tab.positions.index(row)) for row in (0, 1, 5)] == [False, True, True]


def test_a_closed_rows_hidden_meaning_is_its_tooltip(qtbot, deck, off, monkeypatch):
    shown = []
    monkeypatch.setattr(
        "tarot_canvas.ui.canvas.reading_pane.QToolTip.showText",
        lambda pos, text, *args: shown.append(text),
    )
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    tab.turn_next()
    tab.turn_next()
    view = tab.pane.list_view
    # Row 0 is turned and closed: its card's name stands where its meaning was
    point = view.visualRect(tab.positions.index(0)).center()

    QApplication.sendEvent(
        view.viewport(), QHelpEvent(QEvent.Type.ToolTip, point, view.viewport().mapToGlobal(point))
    )

    assert shown == [" ".join(tab.slots()[0].meaning.split())]


def test_double_clicking_a_row_below_the_open_one_opens_its_card(qtbot, deck, off):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    read(qtbot, tab)
    view = tab.pane.list_view
    view.setCurrentIndex(tab.positions.index(0))
    qtbot.wait(10)
    opened = []
    tab.navigation_requested.connect(lambda kind, data: opened.append(data["card"]["id"]))
    point = QPointF(view.visualRect(tab.positions.index(2)).center())
    viewport = view.viewport()

    for kind, buttons in (
        (QEvent.Type.MouseButtonPress, LEFT),
        (QEvent.Type.MouseButtonRelease, NONE),
        (QEvent.Type.MouseButtonDblClick, LEFT),
        (QEvent.Type.MouseButtonRelease, NONE),
    ):
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                kind,
                point,
                QPointF(viewport.mapToGlobal(point.toPoint())),
                LEFT,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    assert opened == [tab.placements[2].card.card_data["id"]]


def test_a_turned_row_names_its_card_and_says_reversed_in_words(qtbot, deck, off, all_reversed):
    tab = make_tab(qtbot)
    deal(qtbot, tab)
    tab.turn_next()
    rows = tab.pane.rows

    name = tab.placements[0].card.card_data["name"]
    assert rows.card_line(tab.positions.index(0)) == READINGS["card_reversed"].format(card=name)
    assert rows.card_line(tab.positions.index(1)) is None


# -- the tab


def test_the_tab_is_titled_by_the_question_cut_short(qtbot, deck):
    tab = make_tab(qtbot)
    assert tab.tab_title() == "Celtic Cross"
    assert tab.tab_tooltip() == ""

    question = "What should I make of the long winter ahead, and of the work it brings?"
    tab.rename(question)

    assert tab.question() == question
    assert tab.tab_title().endswith("…")
    assert len(tab.tab_title()) < len(question)
    assert tab.tab_tooltip() == question


def test_a_reading_saves_nothing_and_closes_without_asking(qtbot, deck, off, monkeypatch):
    def no_prompt(*_):
        raise AssertionError("closing a reading asked")

    monkeypatch.setattr("tarot_canvas.ui.main_window.QMessageBox.warning", no_prompt)
    monkeypatch.setattr(QMessageBox, "question", no_prompt)
    window = MainWindow()
    qtbot.addWidget(window)
    tab = window.open_reading(BUNDLED_SPREADS_PATH / "celtic-cross")
    assert isinstance(tab, ReadingTab)
    assert window.tab_widget.currentWidget() is tab
    deal(qtbot, tab)

    assert not tab.can_save()
    assert not tab.has_unsaved_changes()
    window.tab_widget.tabCloseRequested.emit(window.tab_widget.indexOf(tab))
    assert window.tab_widget.indexOf(tab) == -1


def test_a_spread_that_wont_load_opens_no_reading(qtbot, deck, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    count = window.tab_widget.count()

    assert window.open_reading(tmp_path / "missing") is None
    assert window.tab_widget.count() == count


def test_start_reading_on_a_library_row_opens_one(qtbot, deck, spreads_base):
    from tarot_canvas.ui.library.tab import LibraryTab

    window = MainWindow()
    qtbot.addWidget(window)
    library = LibraryTab()
    window.tab_widget.addTab(library, "Library")

    library.spreads_page.reading_requested.emit(BUNDLED_SPREADS_PATH / "three-card")

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 3


def test_the_keyboard_alone_starts_a_celtic_cross_from_any_library_view(
    qtbot, deck, spreads_base, monkeypatch
):
    from tarot_canvas.settings import LIBRARY_VIEW_KEY, LIBRARY_VIEW_NOTES

    monkeypatch.setattr(spreads, "included_base", lambda: BUNDLED_SPREADS_PATH)
    get_settings().setValue(LIBRARY_VIEW_KEY, LIBRARY_VIEW_NOTES)
    window = MainWindow()
    qtbot.addWidget(window)
    with qtbot.waitActive(window):
        window.show()
        window.activateWindow()
    ctrl = Qt.KeyboardModifier.ControlModifier

    def press(key, modifiers=Qt.KeyboardModifier.NoModifier):
        qtbot.keyClick(QApplication.focusWidget() or window, key, modifiers)

    press(Qt.Key.Key_L, ctrl)
    press(Qt.Key.Key_4, ctrl)
    press(Qt.Key.Key_F, ctrl)
    qtbot.keyClicks(QApplication.focusWidget(), "Cross")
    press(Qt.Key.Key_Down)
    press(Qt.Key.Key_Return, ctrl)

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, ReadingTab)
    assert len(tab.slots()) == 10


# -- every position filled by hand


@pytest.fixture
def themed(monkeypatch):
    """The theme icons the player bar asks for, in order: offscreen has no theme to show them"""
    asked = []
    from_theme = strip_module.QIcon.fromTheme

    def spy(name, *args):
        asked.append(name)
        return from_theme(name, *args)

    monkeypatch.setattr(strip_module.QIcon, "fromTheme", spy)
    return asked


def fill_by_hand(tab, deck, slots):
    cards = deck.get_all_cards()
    return [
        tab.add_specific_card(cards[slot.number], deck, False, slot.sceneBoundingRect().center())
        for slot in slots
    ]


def test_with_every_position_filled_by_hand_the_reading_just_begins(qtbot, deck, off, themed):
    tab = make_tab(qtbot, three_card())
    pane = tab.pane

    placed = fill_by_hand(tab, deck, tab.slots()[:2])
    assert tab.bar.deal.text() == READINGS["deal"]
    assert pane.deck_combo.isEnabled() and pane.reversals_check.isEnabled()

    placed += fill_by_hand(tab, deck, tab.slots()[2:])
    assert tab.bar.deal.text() == READINGS["begin"]
    assert themed[-1] == FINISH_ICON
    assert not pane.deck_combo.isEnabled()
    assert not pane.reversals_check.isEnabled()

    QTest.mouseClick(tab.bar.deal, LEFT)

    assert tab.phase is Phase.READ
    assert [placement.card for placement in tab.placements] == placed
    assert not any(isinstance(card, ReadingCard) for card in tab.cards())
    assert pane.reversals_label.isHidden()
    assert pane.reversals_mark.isHidden()
    assert pane.deck_label.text() == deck.get_name()


def test_taking_a_card_back_off_its_socket_puts_the_deal_back(qtbot, deck, off, themed):
    tab = make_tab(qtbot, three_card())
    last = fill_by_hand(tab, deck, tab.slots())[-1]
    assert tab.bar.deal.text() == READINGS["begin"]

    tab.scene.clearSelection()
    last.setSelected(True)
    tab.delete()

    assert tab.bar.deal.text() == READINGS["deal"]
    assert themed[-1] == DEAL_ICON
    assert tab.pane.deck_combo.isEnabled()


def test_the_deck_line_names_every_deck_the_cards_came_from(
    qtbot, deck, off, tmp_path, stub_deck_manager
):
    other = TarotDeck(str(write_full_deck(tmp_path / "other", name="Other")))
    stub_deck_manager.get_all_decks = lambda: [deck, other]
    tab = make_tab(qtbot, three_card())
    fill_by_hand(tab, other, tab.slots()[:1])

    deal(qtbot, tab)

    assert tab.pane.deck_label.text().split("\n") == [other.get_name(), deck.get_name()]
    assert not tab.pane.reversals_label.isHidden()


# -- the remembered deck


def test_a_new_reading_starts_with_the_deck_last_chosen(
    qtbot, deck, off, tmp_path, stub_deck_manager
):
    other = TarotDeck(str(write_full_deck(tmp_path / "other", name="Other")))
    stub_deck_manager.get_all_decks = lambda: [deck, other]
    first = make_tab(qtbot)
    assert first.deck is deck

    first.pane.deck_combo.setCurrentIndex(first.pane.deck_combo.findData(other))

    assert get_readings_deck() == other.deck_path
    second = make_tab(qtbot)
    assert second.deck is other
    assert second.pane.deck_combo.currentData() is other


def test_a_remembered_deck_since_removed_gives_way_to_the_reference(qtbot, deck, off):
    set_readings_deck("/no/such/deck")

    assert make_tab(qtbot).deck is deck


# -- review fixes


def test_a_card_laid_loose_before_the_deal_is_not_dealt_again(qtbot, short_deck, off):
    tab = make_tab(qtbot, three_card())
    loose = short_deck.get_all_cards()[0]
    far = tab.slots()[-1].sceneBoundingRect().bottomRight() + QPointF(2000, 2000)
    tab.add_specific_card(loose, short_deck, False, far)

    deal(qtbot, tab)

    assert loose["id"] not in {card.card_data["id"] for card in tab.turn_order()}
    assert len(tab.turn_order()) == 2


def test_summon_mid_deal_draws_no_card_still_in_flight(qtbot, short_deck):
    at_level("Reactive")
    tab = make_tab(qtbot, three_card())
    tab.deal()
    assert tab.is_dealing()

    tab.on_draw_card()

    qtbot.waitUntil(lambda: not tab.is_dealing(), timeout=5000)
    ids = [card.card_data["id"] for card in tab.cards() if not isinstance(card, SocketItem)]
    assert len(ids) == len(set(ids)) == 3


def test_a_card_whose_art_wont_load_gives_way_to_the_next(qtbot, deck, off, monkeypatch):
    toasts = []
    monkeypatch.setattr(ReadingTab, "_toast", lambda self, text: toasts.append(text))
    broken = deck.get_all_cards()[0]["id"]
    make = CanvasTab.make_card_item

    def failing(self, card, *args, **kwargs):
        return None if card.get("id") == broken else make(self, card, *args, **kwargs)

    monkeypatch.setattr(CanvasTab, "make_card_item", failing)
    monkeypatch.setattr(
        random, "sample", lambda pool, k: sorted(pool, key=lambda c: c["id"] != broken)
    )
    tab = make_tab(qtbot)

    deal(qtbot, tab)

    assert all(placement.card is not None for placement in tab.placements)
    assert broken not in {card.card_data["id"] for card in tab.turn_order()}
    assert toasts == []


def test_a_reading_opens_with_no_deck_installed(qtbot, deck, off, stub_deck_manager):
    stub_deck_manager.get_reference_deck = lambda: None
    stub_deck_manager.get_all_decks = lambda: []

    tab = make_tab(qtbot)
    tab.deal()

    assert tab.deck is None
    assert tab.phase is Phase.STAGED


def test_ctrl_wheel_does_not_turn_a_socket(qtbot, deck, off):
    tab = make_tab(qtbot, three_card())
    socket = tab.slots()[0]
    viewport = tab.view.viewport()
    pos = centre_on_screen(tab, socket)

    QApplication.sendEvent(
        viewport,
        QWheelEvent(
            QPointF(pos),
            QPointF(viewport.mapToGlobal(pos)),
            QPoint(),
            QPoint(0, 120),
            NONE,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )

    assert [slot.orient for slot in tab.slots()] == [0.0, 0.0, 0.0]


def test_home_and_the_tab_icon_leave_out_filled_sockets(qtbot, deck, off):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    read(qtbot, tab)
    away = QPointF(20000, 20000)
    for card in tab.turn_order():
        card.setPos(card.pos() + away)
    tab.layout_changed.emit()

    tab.on_home()
    tab.refresh_tab_icon()

    visible = tab.view.mapToScene(tab.view.viewport().rect()).boundingRect()
    assert not any(visible.intersects(slot.sceneBoundingRect()) for slot in tab.slots())
    assert len(tab._tab_marks) == len(tab.turn_order())


def test_the_pane_reads_the_staged_table_once_per_change(qtbot, deck, off, monkeypatch):
    tab = make_tab(qtbot)
    calls = []
    scan = ReadingTab._filled_by_hand
    monkeypatch.setattr(ReadingTab, "_filled_by_hand", lambda self: calls.append(1) or scan(self))
    tab.layout_changed.emit()

    for slot in tab.slots():
        tab.card_in(slot)
    assert len(calls) == 1

    first = tab.slots()[0]
    staged = tab.add_specific_card(
        deck.get_all_cards()[0], deck, False, first.sceneBoundingRect().center()
    )
    assert tab.card_in(first) is staged


# -- the halo, the rim light and the candle


def halos(tab):
    return [item for item in tab.scene.items() if isinstance(item, HaloItem)]


def settled(tab):
    return not tab.halo.pending and tab.halo.is_steady()


@pytest.mark.parametrize("level", LEVELS)
def test_one_halo_moves_to_each_next_card_and_goes_after_the_last(qtbot, deck, level):
    at_level(level)
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    qtbot.waitUntil(lambda: settled(tab), timeout=5000)

    for placement in tab.placements:
        assert len(halos(tab)) == 1
        assert tab.halo.card is placement.card
        assert tab.caption.slot is placement.slot
        card = placement.card
        tab.turn_next()
        qtbot.waitUntil(lambda c=card: settled(tab) and not c.is_turning(), timeout=5000)

    assert tab.halo.card is None
    assert not tab.halo.isVisible()
    assert tab.caption.slot is None


@pytest.mark.parametrize("level", ("Full", "Reactive"))
def test_a_turn_flares_then_collapses_and_the_caption_fades_with_it(qtbot, deck, level):
    at_level(level)
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    qtbot.waitUntil(lambda: settled(tab), timeout=5000)
    first = tab.halo.card
    steady = tab.halo.light()

    tab.turn_next()
    qtbot.waitUntil(lambda: tab.halo.light() > steady, timeout=2000)
    qtbot.waitUntil(lambda: tab.halo.collapse is not None, timeout=2000)
    assert tab.halo.card is first
    qtbot.waitUntil(lambda: 0.0 < tab.caption.opacity < 1.0, timeout=2000)
    assert tab.caption.opacity == pytest.approx(tab.halo.fade())
    qtbot.waitUntil(lambda: tab.halo.card is tab.placements[1].card, timeout=2000)
    assert tab.caption.slot is tab.placements[1].slot


@pytest.mark.parametrize("level", LEVELS)
def test_reveal_all_lets_the_halo_go_once_and_leaves_nothing_lit(qtbot, deck, level, monkeypatch):
    at_level(level)
    flares = []
    real = HaloItem.flare
    monkeypatch.setattr(HaloItem, "flare", lambda self, *a: (flares.append(a), real(self, *a)))
    tab = make_tab(qtbot)
    deal(qtbot, tab)

    read(qtbot, tab)
    qtbot.waitUntil(lambda: tab.halo.card is None, timeout=5000)

    assert [pending for pending, _animate in flares] == [None]
    assert tab.halo.light() == 0.0
    assert tab.caption.slot is None
    assert tab.patch.alpha == 0 or not tab.patch.isVisible()


def test_every_back_catches_the_halos_light_falling_with_distance(qtbot, deck, off):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    first, second, third = (p.card for p in tab.placements)

    assert first.rim == pytest.approx(tab.halo.light())
    assert first.rim > second.rim > third.rim > 0.0
    tab.view.viewport().grab()

    tab.turn_next()
    assert second.rim == pytest.approx(tab.halo.light())
    assert third.rim < second.rim


def test_a_decks_own_back_is_rimmed_square_and_the_house_back_round(qtbot, deck, off, monkeypatch):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    assert all(p.card._house_back for p in tab.placements)
    tab.view.viewport().grab()

    own = str(next(iter(sorted(Path(deck.deck_path).rglob("*.png")))))
    monkeypatch.setattr(type(deck), "get_card_backs", lambda self: ({"default": own}, "default"))
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    assert not any(p.card._house_back for p in tab.placements)
    assert tab.placements[0].card.rim > 0.0
    tab.view.viewport().grab()


@pytest.mark.parametrize("level", LEVELS)
def test_the_candle_dims_while_face_down_and_lifts_once_read(qtbot, deck, level):
    at_level(level)
    tab = make_tab(qtbot, three_card())
    assert tab.candle.level == 0.0

    deal(qtbot, tab)
    qtbot.waitUntil(lambda: tab.candle.level == 1.0, timeout=3000)
    assert tab.patch.alpha > 0
    tab.view.viewport().grab()

    read(qtbot, tab)
    qtbot.waitUntil(lambda: tab.candle.level == 0.0, timeout=3000)


def test_a_light_ground_dims_toward_a_tone_of_itself_not_black(qtbot, deck, off):
    ground = QColor("#e8dcc8")
    tab = make_tab(qtbot, three_card())
    tab.view.setBackgroundBrush(ground)
    tab.set_ground(ground)
    deal(qtbot, tab)
    # Far enough out that the corner is past the candle's reach
    tab.view.scale(0.1, 0.1)

    corner = tab.view.viewport().grab().toImage().pixelColor(2, 2)
    dim = dim_tone(ground)
    for channel in ("red", "green", "blue"):
        a, b = getattr(ground, channel)(), getattr(dim, channel)()
        assert getattr(corner, channel)() == pytest.approx(a + (b - a) * CANDLE_ALPHA, abs=3)
    assert dim.hslHue() == pytest.approx(ground.hslHue(), abs=6)
    assert dim.lightness() > 40


def test_at_full_the_halo_flickers_and_sparks(qtbot, deck):
    at_level("Full")
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    qtbot.waitUntil(lambda: len(tab.halo.particles) > 10, timeout=3000)
    seen = set()
    qtbot.waitUntil(
        lambda: (seen.add(round(tab.halo.brightness, 3)), len(seen) > 3)[1], timeout=3000
    )
    assert tab._clock_on
    tab.view.viewport().grab()


def test_reactive_marks_the_next_card_with_a_still_bloom(qtbot, deck):
    at_level("Reactive")
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    qtbot.waitUntil(lambda: settled(tab) and tab.candle.is_still(), timeout=3000)
    qtbot.waitUntil(lambda: not tab._clock_on, timeout=1000)

    assert tab.halo.particles == []
    assert tab.halo.brightness == HALO_STEADY
    assert tab.halo.light() == pytest.approx(HALO_STEADY)


def test_off_lights_everything_at_once_and_runs_no_clock(qtbot, deck, off):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)

    assert not tab._clock_on
    assert tab.halo.fade() == 1.0
    assert tab.candle.level == 1.0
    assert tab.caption.opacity == 1.0
    assert tab.placements[1].card.rim > 0.0
    tab.turn_next()
    assert tab.halo.card is tab.placements[1].card
    assert not tab._clock_on


def test_hiding_the_tab_mid_flare_moves_the_halo_on(qtbot, deck):
    at_level("Full")
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    tab.turn_next()
    tab.hide()

    assert tab.halo.card is tab.placements[1].card
    assert tab.halo.is_steady()
    assert tab.halo.particles == []


def test_home_leaves_out_the_halos_light(qtbot, deck, off):
    tab = make_tab(qtbot, three_card())
    deal(qtbot, tab)
    tab.on_home()
    lit = tab.view.transform()

    tab.halo.setVisible(False)
    tab.patch.setVisible(False)
    tab.on_home()
    assert tab.view.transform() == lit
