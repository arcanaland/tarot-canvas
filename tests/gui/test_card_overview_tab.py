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
