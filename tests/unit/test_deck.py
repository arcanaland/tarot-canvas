def test_minimal_deck_loads_expected_cards(minimal_deck):
    cards = minimal_deck.get_all_cards()

    assert len(cards) == 2
    assert {c["id"] for c in cards} == {"major_arcana.00", "major_arcana.01"}

    names = {c["id"]: c["name"] for c in cards}
    assert names["major_arcana.00"] == "The Fool"
    assert names["major_arcana.01"] == "The Magician"
