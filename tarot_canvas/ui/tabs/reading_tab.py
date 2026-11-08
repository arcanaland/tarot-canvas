"""A tarot reading dealt from a spread"""

import os
import random

from PyQt6.QtCore import QDateTime, QItemSelectionModel, QLineF, QRectF, QSignalBlocker, Qt, QTimer
from PyQt6.QtGui import QFontMetrics, QIcon
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    get_readings_deck,
    get_readings_reversals,
    set_readings_deck,
    set_readings_reversals,
)
from tarot_canvas.ui.canvas.backs import back_pixmap
from tarot_canvas.ui.canvas.candle import Candle, WarmPatch
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.halo import HaloItem
from tarot_canvas.ui.canvas.placement import (
    DIM_IN_S,
    DIM_LIFT_S,
    FACE_DOWN_GROUND_PACE,
    Phase,
    Placement,
    SocketItem,
)
from tarot_canvas.ui.canvas.reading_card import (
    FLIGHT_S,
    REACTIVE_FLIGHT_S,
    Flights,
    ReadingCard,
    is_face_down,
)
from tarot_canvas.ui.canvas.reading_marks import Badges, Caption
from tarot_canvas.ui.canvas.reading_pane import ReadingPane, RowOpener
from tarot_canvas.ui.canvas.reading_strip import ReadingStrip, RevealKeys
from tarot_canvas.ui.canvas.slot_item import SlotItem
from tarot_canvas.ui.card_transfer import deck_path_key
from tarot_canvas.ui.icons import SPREAD_ICON
from tarot_canvas.ui.strings import CANVAS, READINGS, SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_slots import SpreadSlots
from tarot_canvas.utils.logger import logger

# Seconds between turns under Reveal All
TURN_ALL_GAP_S = 0.15

CARD_Z = 10000.0
FLIGHT_Z = 30000.0
NEXT_Z = 40000.0
TURNING_Z = 40001.0

# About how many characters of the Question the tab shows
TAB_TITLE_CHARS = 32

# A face-down neighbour's share of the next card's light, at no distance, and how far away in
# position heights it has none
RIM_NEIGHBOUR = 0.45
RIM_REACH = 2.5
# The table the candle lights is the positions' bounds, this much bigger on each side by its longer
# side
TABLE_PAD = 0.05


def _centre(item):
    return item.pos() + item.boundingRect().center()


def remembered_deck():
    """The deck the user last read with"""
    wanted = deck_path_key(get_readings_deck())
    if wanted is not None:
        for deck in deck_manager.get_all_decks():
            if deck_path_key(deck.deck_path) == wanted:
                return deck
    return deck_manager.get_reference_deck()


class ReadingTab(SpreadSlots, CanvasTab):
    """A spread opened to deal a reading from"""

    TOOLS_TITLE = CANVAS["section_cards"]
    SLOT_ITEM = SocketItem

    phase = Phase.STAGED
    _flights = None
    halo = None
    candle = None

    # {socket: card} filled by hand, until the table next changes
    _by_hand = None

    def __init__(self, spread, parent=None):
        super().__init__(parent)
        self.init_slots()
        self.spread = spread
        self.phase = Phase.STAGED
        self.dealt_at = None
        # Every card that fills a position, in number order: the order they turn and are stepped
        self._order = []
        # The cards dealt face-down, and those still to turn, in number order
        self._dealt = []
        self._turn_queue = []
        self._landed = set()
        self._flights = Flights(self.scene)
        # Seconds until Reveal All's next turn, or None
        self._cascade_wait = None
        # Under Reveal All the halo has let go, and stays gone
        self._revealing_all = False
        self._clock_on = False
        self._syncing = False

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.replaceWidget(self.canvas_area, self.splitter)
        self.splitter.addWidget(self.canvas_area)
        remembered = remembered_deck()
        self.pane = ReadingPane(
            self,
            self.positions,
            spread.name,
            spread.description,
            deck_manager.get_all_decks(),
            remembered,
        )
        self.pane.dock(self.splitter)
        self.deck = self.pane.chosen_deck() or remembered
        self.pane_action = self.pane.toggle_action(self, SPREADS["pane_tooltip"])

        self.lay_out_slots(spread.positions, card_unit_size().width())
        self.placements = [Placement(slot) for slot in self._slots]
        self._connect_pane()
        self._build_strip()

        self.badges = Badges(self.view, self._badge_marks)
        self.caption = Caption(self.view)
        self.candle = Candle(self.view, self._table_rect, lambda: self.ground)
        self.patch = WarmPatch()
        self.scene.addItem(self.patch)
        self.halo = HaloItem(self.view, self._halo_moved)
        self.scene.addItem(self.halo)
        # The candle under the marks, and the caption last, over everything
        self.view.foreground_hooks.extend((self.candle, self.badges, self.caption))
        self._reveal_keys = RevealKeys(self, self.view, self.pane.list_view)

        # First, so every reader below sees the table as it now is
        self.layout_changed.connect(self._forget_by_hand)
        self.layout_changed.connect(self.refresh_rows)
        # A card dropped on, or moved off, a socket may change what the deal will do
        self.layout_changed.connect(self._sync_staging)
        self.scene.selectionChanged.connect(self.show_selection)

        self._home_timer = QTimer(self)
        self._home_timer.setSingleShot(True)
        self._home_timer.setInterval(0)
        self._home_timer.timeout.connect(self.on_home)
        self._home_on_show = True
        self.set_phase(Phase.STAGED)

    def _connect_pane(self):
        pane = self.pane
        pane.question_edit.textChanged.connect(self.tab_label_changed)
        pane.question_edit.submitted.connect(self.deal)

        pane.deck_combo.currentIndexChanged.connect(self._on_deck_chosen)

        # The user's last choice, from any reading
        pane.reversals_check.setChecked(get_readings_reversals())
        pane.reversals_check.toggled.connect(set_readings_reversals)

        selection = pane.list_view.selectionModel()
        selection.selectionChanged.connect(self.refresh_rows)
        selection.selectionChanged.connect(self._on_row_selected)

        # A row chosen again, its card turned since, selects it too
        pane.list_view.clicked.connect(self._on_row_selected)
        self._row_opener = RowOpener(pane.list_view, self._open_row_card)

    def _build_strip(self):
        """View's actions and the pane's toggle leave the rail for a strip under the canvas, in a
        column of their own beside the rail. Their keys stay the tab's"""
        for action in self.view_section:
            self.toolbar.removeAction(action)
        self.strip = ReadingStrip(self, [*self.view_actions, self.pane_action])
        self.bar = self.strip.bar
        column = QWidget()
        stack = QVBoxLayout(column)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        self.canvas_area.layout().replaceWidget(self.view, column)
        stack.addWidget(self.view, 1)
        stack.addWidget(self.strip)
        # A table, not an infinite canvas: the cards fit, and middle- or Shift-drag still pans
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # -- the canvas's commands, as a reading has them ---------------------------------------

    def command_handlers(self):
        handlers = super().command_handlers()
        # Saves nothing
        del handlers["canvas.save_layout_as_spread"]
        return handlers

    def on_draw_card(self, at=None):
        # If we haven't dealt the cards yet, deal the cards first
        if self.phase is Phase.STAGED:
            self.deal()
            return
        taken = self._taken_ids()
        pool = [card for card in self._pool() if card.get("id") not in taken]
        if not pool:
            logger.info("Every card of the reading's deck is on the table")
            return
        self.add_specific_card(random.choice(pool), self.deck, self._draw_reversed(), at)

    def card_menu(self, scene_pos):
        item = self.card_at(scene_pos)
        if item is None or isinstance(item, SlotItem) or is_face_down(item):
            return None
        return super().card_menu(scene_pos)

    def build_card_menu(self, item):
        if isinstance(item, SlotItem) or is_face_down(item):
            return None
        return super().build_card_menu(item)

    def on_turn_card_by_wheel(self, card, notches, fine):
        if not isinstance(card, SlotItem) and not is_face_down(card):
            super().on_turn_card_by_wheel(card, notches, fine)

    def cards(self):
        return tuple(card for card in self._cards if card.isVisible())

    def register_card(self, card):
        super().register_card(card)
        self._forget_by_hand()

    def unregister_card(self, card):
        super().unregister_card(card)
        self._forget_by_hand()

    def set_ground(self, color):
        super().set_ground(color)
        for card in self._cards:
            if isinstance(card, SocketItem):
                card.redraw()
        self.view.viewport().update()

    def ambient_is_allowed(self):
        """Still until every card has landed and turned, then as any canvas"""
        return self.phase is Phase.READ and super().ambient_is_allowed()

    def empty_tab_icon(self):
        return QIcon.fromTheme(SPREAD_ICON)

    # -- placements, rows and selection ----------------------------------------------------

    def placement_of(self, card):
        return next((p for p in self.placements if p.card is card), None)

    def _placement_at(self, slot):
        return self.placements[self._slots.index(slot)]

    def card_in(self, slot):
        """The card in a given slot (either dealt or manually placed)"""
        if self.phase is Phase.STAGED:
            return self._staged_by_hand().get(slot)
        card = self._placement_at(slot).card
        if card in self._dealt and card not in self._landed:
            return None
        return card

    def is_next_slot(self, slot):
        following = self.next_card()
        return following is not None and self.placement_of(following).slot is slot

    def refresh_rows(self):
        """Open the selected row and the next card's, and paint the rows again"""
        view = self.pane.list_view
        rows = {index.row() for index in view.selectionModel().selectedRows()}
        following = self.next_card()
        if following is not None:
            rows.add(self.placements.index(self.placement_of(following)))
        self.pane.rows.set_open_rows(rows)
        view.viewport().update()

    def show_selection(self):
        """The canvas's selection, shown as the row of the one selected card's position"""
        self._sync_delete()
        if self.phase is Phase.READ:
            self.bar.sync()
        if self._syncing:
            return
        selected = self.selected_cards()
        placement = self.placement_of(selected[0]) if len(selected) == 1 else None
        selection = self.pane.list_view.selectionModel()
        self._syncing = True
        try:
            if placement is None:
                selection.clearSelection()
            else:
                index = self.positions.index(self.placements.index(placement))
                selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                self.pane.list_view.scrollTo(index)
        finally:
            self._syncing = False

    def _on_row_selected(self, *_):
        """A row chosen in the pane selects its position's card, once it is face-up"""
        rows = self.pane.list_view.selectionModel().selectedRows()
        if self._syncing or len(rows) != 1:
            return
        card = self.placements[rows[0].row()].card
        if card is None or card.scene() is None or is_face_down(card):
            return
        self._syncing = True
        try:
            self._select_card(card)
        finally:
            self._syncing = False

    def _select_card(self, card):
        with QSignalBlocker(self.scene):
            self.scene.clearSelection()
        card.setSelected(True)
        self.view.ensureVisible(card.sceneBoundingRect(), 40, 40)

    def _open_row_card(self, row):
        """Open the card on row's position, if it is face-up"""
        card = self.card_in(self._slots[row])
        if card is None or is_face_down(card):
            return False
        self.open_card_view(card)
        return True

    def open_current_row(self):
        index = self.pane.list_view.currentIndex()
        return index.isValid() and self._open_row_card(index.row())

    # -- deleting: the reading's cards stay; only extras go --------------------------------

    def _extras(self):
        """Selected cards that fill no position: summoned, pasted or dropped after the deal"""
        return [card for card in self.selected_cards() if self.placement_of(card) is None]

    def _sync_delete(self):
        if not self.arranging:
            self.commands["canvas.delete"].setEnabled(bool(self._extras()))

    def can_delete(self):
        return not self.arranging and bool(self._extras())

    def can_cut_card(self):
        return self.can_copy_card() and self.can_delete()

    def on_delete_card(self):
        """Remove the selected extras"""
        extras = self._extras()
        for card in extras:
            self.scene.removeItem(card)
        if extras:
            self.layout_changed.emit()

    def swap_card(self, item, deck, card):
        """The position moves to the replacement"""
        placement = self.placement_of(item)
        replacement = super().swap_card(item, deck, card)
        if replacement is not None and placement is not None:
            placement.fill(replacement, by_hand=placement.by_hand)
            self._order[self._order.index(item)] = replacement
            self._landed.add(replacement)
            self.refresh_rows()
        return replacement

    # -- the question, the deck and reversals -----------------------------------------------

    def question(self):
        return self.pane.question_edit.text().strip()

    def reversals(self):
        return self.pane.reversals_check.isChecked()

    def _draw_reversed(self):
        return self.reversals() and random.random() < 0.5

    def _on_deck_chosen(self):
        if self.phase is Phase.STAGED:
            self.deck = self.pane.chosen_deck()
            # The next reading starts with it too
            set_readings_deck(self.deck.deck_path if self.deck is not None else "")
            self.refresh_rows()

    def display_name(self):
        return self.question() or self.spread.name or SPREADS["untitled"]

    def tab_title(self):
        metrics = QFontMetrics(self.font())
        width = metrics.averageCharWidth() * TAB_TITLE_CHARS
        return metrics.elidedText(self.display_name(), Qt.TextElideMode.ElideRight, width)

    def tab_tooltip(self):
        name = self.display_name()
        return name if name != self.tab_title() else ""

    def rename_text(self):
        return self.question()

    def rename(self, name):
        self.pane.question_edit.setText(name)

    def can_save(self):
        return False

    def has_unsaved_changes(self):
        return False

    # -- the phase --------------------------------------------------------------------------

    def set_phase(self, phase):
        self.phase = phase
        # The ground slows while any card is face-down, and comes back once all are turned
        if phase is Phase.DEALT:
            self.ground_pace.set_target(FACE_DOWN_GROUND_PACE, DIM_IN_S)
        else:
            self.ground_pace.set_target(1.0, DIM_LIFT_S)
        self.candle.set_lit(phase is Phase.DEALT, self.motion_level != "Off")
        self._wake()
        self._sync_facts()

        # No rail until every card is turned
        self.toolbar.setVisible(phase is Phase.READ)
        self.bar.sync()
        self.edit_state_changed()

    def _sync_facts(self):
        if self.phase is Phase.STAGED:
            decks = [self.deck] if self.deck is not None else []
            self.pane.sync(self.phase, decks, self.reversals(), None, not self.all_placed())
            return
        # The decks the cards came from, not the menu's: cards placed by hand may be any deck's
        decks = []
        for card in self._order:
            if card.deck is not None and card.deck not in decks:
                decks.append(card.deck)
        reversals = self.reversals() if self._dealt else None
        if not decks and self.deck is not None:
            decks.append(self.deck)
        self.pane.sync(self.phase, decks, reversals, self.dealt_at)

    def _sync_staging(self):
        if self.phase is Phase.STAGED:
            self._sync_facts()
            self.bar.sync()

    def all_placed(self):
        """Whether every position is filled by hand, so the deal would draw nothing"""
        return self.phase is Phase.STAGED and len(self._staged_by_hand()) == len(self._slots)

    def can_turn(self):
        """Whether a card waits to be turned and every card has landed"""
        return self.phase is Phase.DEALT and not self.is_dealing() and bool(self._turn_queue)

    def next_card(self):
        return self._turn_queue[0] if self.can_turn() else None

    def turn_order(self):
        return tuple(self._order)

    def has_landed(self, card):
        return card in self._landed

    def is_dealing(self):
        return self._flights is not None and self._flights.is_active()

    # -- staging ----------------------------------------------------------------------------

    def _pool(self):
        """The deck's cards that can be drawn: those with a face to turn up"""
        cards = list(self.deck.get_all_cards()) if self.deck is not None else []
        return [card for card in cards if card.get("image") and os.path.exists(card["image"])]

    def _taken_ids(self):
        """Ids of the cards the deck can't give again"""
        placed = [p.card for p in self.placements if p.card is not None]
        loose = [
            card
            for card in self.cards()
            if not isinstance(card, SlotItem) and card.deck is self.deck
        ]
        return {card.card_data.get("id") for card in (*placed, *loose)}

    def _forget_by_hand(self):
        self._by_hand = None

    def _staged_by_hand(self):
        if self._by_hand is None:
            self._by_hand = self._filled_by_hand()
        return self._by_hand

    def _filled_by_hand(self):
        """{socket: card} for face-up cards whose centre lies in an empty socket"""
        filled = {}
        for card in self.cards():
            if isinstance(card, SlotItem | ReadingCard):
                continue
            centre = _centre(card)
            for slot in self._slots:
                if slot not in filled and slot.sceneBoundingRect().contains(centre):
                    filled[slot] = card
                    break
        return filled

    # -- dealing ----------------------------------------------------------------------------

    def deal(self):
        """Fill the empty positions from the deck, face-down, in number order"""
        if self.phase is not Phase.STAGED or self.deck is None:
            return
        self.refresh_motion_settings()
        self.dealt_at = QDateTime.currentDateTime()
        self.scene.clearSelection()

        by_hand = self._filled_by_hand()
        for slot, item in by_hand.items():
            item.setPos(_centre(slot) - item.boundingRect().center())
            item.set_orient(slot.orient)
            placement = self._placement_at(slot)
            placement.fill(item, by_hand=True)
            placement.sync_slot(landed=True)
            self._landed.add(item)

        drawable = self._pool()
        faceless = len(self.deck.get_all_cards()) - len(drawable)
        if faceless:
            logger.info(
                f"Left {faceless} cards with no face out of the draw from {self.deck.get_name()}"
            )
        taken = self._taken_ids()
        pool = [card for card in drawable if card.get("id") not in taken]
        empty = [placement for placement in self.placements if placement.card is None]
        self._dealt = self._make_cards(empty, random.sample(pool, len(pool)))
        if len(self._dealt) < len(empty):
            logger.info(f"Short deal: {len(self._dealt)} cards for {len(empty)} positions")
            filled = len(self.placements) - len(empty) + len(self._dealt)
            self._toast(READINGS["short_deal"].format(dealt=filled, positions=len(self.placements)))
        self._turn_queue = list(self._dealt)
        self._order = [p.card for p in self.placements if p.card is not None]
        self.set_phase(Phase.DEALT)
        # The keys that turn are the canvas's, and the Deal button is about to go
        self.view.setFocus(Qt.FocusReason.OtherFocusReason)

        if self.motion_level == "Off":
            for card in self._dealt:
                self._land(card, instant=True)
            self._finish_deal()
            return
        self._launch(self._dealt)

    def _make_cards(self, placements, shuffled):
        backs = {}
        dealt = []
        draw = iter(shuffled)
        for placement in placements:
            item = None
            for card in draw:
                reversed = self._draw_reversed()
                item = self.make_card_item(card, self.deck, reversed, item_type=ReadingCard)
                if item is not None:
                    break
                logger.info(f"Passed over {card.get('name')}: its art won't load")
            if item is None:
                break
            size = item.face_pixmap().size()
            key = (size.width(), size.height())
            if key not in backs:
                backs[key] = back_pixmap(self.deck, size)
            item.lie_face_down(*backs[key])
            placement.fill(item)
            dealt.append(item)
            logger.debug(
                f"Dealt {card.get('name')}{' (reversed)' if reversed else ''} "
                f"to {placement.number} {placement.slot.label!r}"
            )
        return dealt

    def _launch(self, cards):
        """Fly cards in from just below the view"""
        if not cards:
            self._finish_deal()
            return
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        duration = FLIGHT_S if self.motion_level == "Full" else REACTIVE_FLIGHT_S
        flights = [(card, self.placement_of(card).slot) for card in cards]
        self._flights.launch(flights, visible, duration, FLIGHT_Z)
        self._clock(True)

    def _land(self, card, instant):
        slot = self.placement_of(card).slot
        if card.scene() is None:
            self.scene.addItem(card)
        card.setPos(_centre(slot) - card.boundingRect().center())
        card.motion.orient = slot.orient % 360
        card.motion.orient_lag = 0.0
        card.setZValue(CARD_Z + slot.zValue())
        card._apply_motion()
        if not instant:
            card.place_and_settle()
        self._landed.add(card)
        self.placement_of(card).sync_slot(landed=True)
        self.refresh_rows()
        self.bar.sync()
        self.view.viewport().update()

    def _finish_deal(self):
        self._flights.clear()
        self._top_z = max([self._top_z] + [card.zValue() for card in self._dealt])
        if not self._turn_queue:
            self._read()
            return
        self._sync_next()
        self.halo.attach(self.next_card(), fade=self.motion_level != "Off")
        self._wake()

    # -- turning ----------------------------------------------------------------------------

    def _sync_next(self):
        """The next card answers the pointer, lies on top, and its row shows"""
        following = self.next_card()
        for card in self._dealt:
            card.set_next(card is following)
        if following is not None:
            following.setZValue(NEXT_Z)
            index = self.positions.index(self.placements.index(self.placement_of(following)))
            self.pane.list_view.scrollTo(index)
        self.refresh_rows()
        self.bar.sync()
        self.view.viewport().update()

    def card_clicked(self, card):
        if card is self.next_card():
            self.turn_next()

    def turn_next(self):
        if not self.can_turn():
            return
        card = self._turn_queue.pop(0)
        animate = self.motion_level != "Off"
        # Above the next card while it turns, then back to its own depth
        card.setZValue(TURNING_Z)
        self._sync_next()
        if not self._revealing_all:
            self.halo.flare(self.next_card(), animate)
        card.begin_turn(animate)
        self.bar.sync()
        self._wake()

    def turn_all(self):
        """Turn every card left, in order, one after another"""
        if not self.can_turn():
            return
        # The halo means "turn this one next", which Reveal All has answered: it flares once and
        # goes, rather than chase a cascade quicker than its flare
        self._revealing_all = True
        self.halo.flare(None, self.motion_level != "Off")
        if self.motion_level == "Off":
            while self._turn_queue:
                self.turn_next()
            return
        self.turn_next()
        if self._turn_queue:
            self._cascade_wait = TURN_ALL_GAP_S
            self._clock(True)

    def card_revealed(self, card):
        """card's face is up, part way through its turn"""
        self.schedule_detail()
        self.refresh_rows()

    def card_turned(self, card):
        """card's turn is over"""
        placement = self.placement_of(card)
        if placement is not None:
            card.setZValue(CARD_Z + placement.slot.zValue())
        self.refresh_rows()
        if not self._turn_queue and not any(c.is_turning() for c in self._dealt):
            self._read()
        self.bar.sync()

    def _read(self):
        self._cascade_wait = None
        self._revealing_all = False
        self.set_phase(Phase.READ)
        self.layout_changed.emit()

    # -- stepping through a turned reading --------------------------------------------------

    def _steps(self):
        """The reading's cards in number order, those still on the table"""
        return [card for card in self._order if card.scene() is not None and card.isVisible()]

    def stepped_card(self):
        """The one selected card the transport stands on, once every card is turned"""
        if self.phase is not Phase.READ:
            return None
        selected = self.selected_cards()
        if len(selected) == 1 and selected[0] in self._order:
            return selected[0]
        return None

    def _step_index(self, how):
        steps = self._steps()
        if not steps:
            return None
        if how == "first":
            return 0
        if how == "last":
            return len(steps) - 1
        current = self.stepped_card()
        if current not in steps:
            # From nothing selected, Next starts at the first and Previous at the last
            return 0 if how == "next" else len(steps) - 1
        target = steps.index(current) + (1 if how == "next" else -1)
        return target if 0 <= target < len(steps) else None

    def can_step(self, how):
        index = self._step_index(how)
        return index is not None and self._steps()[index] is not self.stepped_card()

    def step(self, how):
        """Select the previous, next, first or last card in number order"""
        if self.phase is not Phase.READ:
            return
        index = self._step_index(how)
        if index is not None:
            self._select_card(self._steps()[index])

    # -- the badges -------------------------------------------------------------------------

    def _badge_marks(self):
        """(card, number, lit) for each filled position whose card has landed"""
        if self.phase is Phase.STAGED:
            return []
        following = self.next_card()
        return [
            (placement.card, placement.number, placement.card is following)
            for placement in self.placements
            if placement.card is not None
            and placement.card.scene() is not None
            and placement.card.isVisible()
            and placement.card in self._landed
        ]

    # -- the halo, the rim light and the candle -------------------------------------------------

    def _table_rect(self):
        """The positions' bounds, padded: the table the candle leaves lit"""
        rect = QRectF()
        for slot in self._slots:
            rect = rect.united(slot.sceneBoundingRect())
        pad = max(rect.width(), rect.height()) * TABLE_PAD
        return rect.adjusted(-pad, -pad, pad, pad)

    def _halo_moved(self, card):
        placement = self.placement_of(card) if card is not None else None
        self.caption.show_for(placement.slot if placement is not None else None)
        self.patch.follow(card)
        self._sync_light()

    def back_light(self, card):
        """The halo's light on a face-down card's edge: all of it on its own card, and a share
        falling off with distance on the others"""
        light = self.halo.light()
        lit = self.halo.card
        if light <= 0.0 or lit is None:
            return 0.0
        if card is lit:
            return light
        # In position heights: a deck's art may be smaller than its positions
        placement = self.placement_of(lit)
        rect = placement.slot.boundingRect() if placement is not None else lit.boundingRect()
        height = rect.height() or 1.0
        d = QLineF(_centre(card), _centre(lit)).length() / height
        falloff = max(0.0, 1.0 - d / RIM_REACH)
        return light * RIM_NEIGHBOUR * falloff * falloff * self.candle.level

    def _sync_light(self):
        """The caption, the warm patch and every face-down back, to the halo and the candle now"""
        fade = self.halo.fade()
        if fade != self.caption.opacity:
            before = self.caption.rect()
            self.caption.opacity = fade
            self.view.viewport().update(before.united(self.caption.rect()).toAlignedRect())
        self.patch.set_strength(self.halo.glow() * self.candle.level)
        for card in self._dealt:
            if card.face_down:
                card.set_rim(self.back_light(card))

    def _needs_clock(self):
        """Whether anything is still moving: a flight, a cascade, a fade, or a lively halo"""
        if self.is_dealing() or self._cascade_wait is not None:
            return True
        if not self.candle.is_still() or not self.halo.is_steady():
            return True
        return self.halo.card is not None and self.motion_level == "Full"

    def _wake(self):
        if self.isVisible() and self._needs_clock():
            self._clock(True)

    # -- the clock --------------------------------------------------------------------------

    def _clock(self, on):
        if on and not self._clock_on and self.motion_level != "Off":
            self.motion_clock.subscribe(self._reading_tick)
            self._clock_on = True
        elif not on and self._clock_on:
            self.motion_clock.unsubscribe(self._reading_tick)
            self._clock_on = False

    def _reading_tick(self, t, dt):
        if self.is_dealing():
            for card in self._flights.advance(t):
                self._land(card, instant=False)
            if not self.is_dealing():
                self._finish_deal()
        if self._cascade_wait is not None:
            self._cascade_wait -= dt
            if self._cascade_wait <= 0.0:
                self.turn_next()
                self._cascade_wait = TURN_ALL_GAP_S if self._turn_queue else None
        self.halo.advance(t, dt, self.motion_level == "Full")
        self.candle.advance(dt)
        self._sync_light()
        if not self._needs_clock():
            self._clock(False)

    def showEvent(self, event):
        super().showEvent(event)
        if self._home_on_show:
            self._home_on_show = False
            self._home_timer.start()
        self._wake()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._clock(False)

    def settle_motion(self):
        super().settle_motion()
        # Hidden mid-deal: every card lands where it was going
        if self.is_dealing():
            for card in self._flights.cards():
                self._land(card, instant=True)
            self._finish_deal()
        if self.halo is not None:
            self.halo.settle()
            self.candle.snap()
            self._sync_light()
