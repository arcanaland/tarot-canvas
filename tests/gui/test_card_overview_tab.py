from types import SimpleNamespace

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QWidget

from tarot_canvas.ui.tabs.card_view.overview_tab import OverviewTab

MAJOR = {
    "name": "Wheel of Fortune",
    "id": "major_arcana.10",
    "type": "major_arcana",
    "number": 10,
    "alt_text": "A large, ornate wheel bearing esoteric symbols.",
}

MINOR = {
    "name": "Three of Cups",
    "id": "minor_arcana.cups.3",
    "type": "minor_arcana",
    "suit": "cups",
    "rank": "three",
}


def make_tab(qtbot, card, deck=None):
    tab = OverviewTab(card, deck)
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


class FakeCardView(QWidget):
    """What the deck link asks of the tab it sits in"""

    navigation_requested = pyqtSignal(str, object)

    def __init__(self, reference_deck):
        super().__init__()
        self.id = "card_1"
        self.deck_manager = SimpleNamespace(get_reference_deck=lambda: reference_deck)


def test_a_broken_link_to_the_reference_deck_survives_a_rescan(qtbot):
    """A rescan swaps every deck object, so the tab's deck is the old one, at the same path"""
    reference = SimpleNamespace(deck_path="/decks/rider-waite-smith")
    before_the_rescan = SimpleNamespace(deck_path="/decks/rider-waite-smith")
    card_view = FakeCardView(reference)
    qtbot.addWidget(card_view)
    tab = OverviewTab(MAJOR, None, card_view)
    tab.deck = before_the_rescan
    asked = []
    card_view.navigation_requested.connect(lambda action, args: asked.append((action, args)))

    tab.on_deck_link_clicked("deck:None")

    assert asked == [
        ("open_deck_view", {"deck_path": reference.deck_path, "source_tab_id": "card_1"})
    ]


def test_info_frame_stays_visible_for_major_arcana(qtbot):
    tab = make_tab(qtbot, MAJOR)

    assert tab.info_frame.isVisible()
    assert tab.number_label.isVisible()
    assert tab.number_value.isVisible()
    assert tab.number_value.text() == "10"
    assert not tab.suit_value.isVisible()
    assert not tab.rank_value.isVisible()


def test_info_frame_stays_visible_for_minor_arcana(qtbot):
    tab = make_tab(qtbot, MINOR)

    assert tab.info_frame.isVisible()
    assert tab.suit_value.text() == "Cups"
    assert tab.rank_value.text() == "Three"
    assert tab.suit_label.isVisible()
    assert tab.rank_label.isVisible()
    assert not tab.number_value.isVisible()


def test_switching_card_type_keeps_the_info_frame(qtbot):
    tab = make_tab(qtbot, MAJOR)

    tab.update_card_info(MINOR, None)
    assert tab.info_frame.isVisible()
    assert tab.suit_value.isVisible()
    assert not tab.number_value.isVisible()

    tab.update_card_info(MAJOR, None)
    assert tab.info_frame.isVisible()
    assert tab.number_value.isVisible()
    assert not tab.suit_value.isVisible()


def test_the_canonical_id_is_in_the_system_fixed_width_font(qtbot):
    tab = make_tab(qtbot, MINOR)
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

    assert tab.id_label.text() == "minor_arcana.cups.3"
    assert tab.id_label.font().family() == fixed.family()
