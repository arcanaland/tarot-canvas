import pytest

from tarot_canvas.models.esoterica_registry import (
    CORRESPONDENCES,
    PASSAGES,
    Role,
    is_divinatory,
    role_of,
    sort_key,
)

PASSAGE_ROLES = [
    ("x_subtitle", Role.EPITHET),
    ("name", Role.EPITHET),
    ("keywords", Role.KEYWORDS),
    ("text", Role.PRINCIPAL),
    ("theme", Role.PRINCIPAL),
    ("light", Role.RANGE),
    ("shadow", Role.RANGE),
    ("personality", Role.CHARACTER),
    ("approach", Role.CHARACTER),
    ("story", Role.CHARACTER),
    ("x_mythical_spiritual", Role.CHARACTER),
    ("questions", Role.PROMPTS),
    ("affirmation", Role.PROMPTS),
    ("x_note", Role.NOTES),
    ("advice.relationships", Role.ADVICE),
    ("advice.work", Role.ADVICE),
    ("advice.spirituality", Role.ADVICE),
    ("advice.personal_growth", Role.ADVICE),
    ("symbols.the_dog", Role.SYMBOLS),
    ("advice.fortune_telling", Role.DIVINATORY),
    ("advice.timing", Role.DIVINATORY),
]

CORRESPONDENCE_ORDER = [
    "number",
    "x_numerology",
    "element",
    "x_elemental_dignity",
    "planet",
    "zodiac",
    "decan",
    "astrology",
    "season",
    "direction",
    "color",
    "archetype",
    "hebrew_letter",
    "hebrew_letter_meaning",
    "hebrew_letter_value",
    "x_hebrew_letter_alt",
]


@pytest.mark.parametrize(("key", "role"), PASSAGE_ROLES)
def test_each_registered_passage_has_its_role(key, role):
    assert role_of(PASSAGES, key) is role


def test_passages_sort_in_registry_order():
    keys = [key for key, _ in PASSAGE_ROLES]
    shuffled = list(reversed(keys))

    ordered = sorted(shuffled, key=lambda k: sort_key(PASSAGES, k, shuffled.index(k)))

    assert ordered == keys


@pytest.mark.parametrize("key", CORRESPONDENCE_ORDER)
def test_each_registered_correspondence_has_the_correspondence_role(key):
    assert role_of(CORRESPONDENCES, key) is Role.CORRESPONDENCES


def test_correspondences_sort_in_registry_order_after_every_reading_passage():
    shuffled = list(reversed(CORRESPONDENCE_ORDER))

    ordered = sorted(shuffled, key=lambda k: sort_key(CORRESPONDENCES, k, shuffled.index(k)))

    assert ordered == CORRESPONDENCE_ORDER
    assert sort_key(PASSAGES, "advice.timing", 99) < sort_key(CORRESPONDENCES, "number", 0)


def test_the_group_note_is_registered_and_sorts_after_correspondences():
    assert role_of(PASSAGES, "x_suit_cards") is Role.GROUP_NOTES
    assert sort_key(CORRESPONDENCES, "x_hebrew_letter_alt", 99) < sort_key(
        PASSAGES, "x_suit_cards", 0
    )


@pytest.mark.parametrize("key", ["numerology", "elemental_dignity"])
def test_an_unprefixed_spelling_takes_the_x_spelling_position(key):
    assert role_of(CORRESPONDENCES, key) is Role.CORRESPONDENCES
    assert sort_key(CORRESPONDENCES, key, 0)[0] == sort_key(CORRESPONDENCES, f"x_{key}", 0)[0]


def test_any_symbol_is_a_symbol_and_symbols_keep_file_order():
    assert role_of(PASSAGES, "symbols.anything") is Role.SYMBOLS
    assert sort_key(PASSAGES, "symbols.zebra", 1) < sort_key(PASSAGES, "symbols.apple", 2)


def test_a_key_in_the_wrong_slot_is_unknown():
    assert role_of(CORRESPONDENCES, "text") is None
    assert role_of(PASSAGES, "element") is None


def test_unknown_keys_have_no_role_and_sort_after_known_keys_of_their_slot():
    assert role_of(PASSAGES, "x_unknown") is None
    assert role_of(CORRESPONDENCES, "x_unknown") is None
    assert role_of(PASSAGES, "advice.health") is None

    assert sort_key(PASSAGES, "x_suit_cards", 99) < sort_key(PASSAGES, "x_unknown", 0)
    assert sort_key(CORRESPONDENCES, "x_hebrew_letter_alt", 99) < sort_key(
        CORRESPONDENCES, "x_unknown", 0
    )
    assert sort_key(PASSAGES, "x_b", 1) < sort_key(PASSAGES, "x_a", 2)


def test_only_fortune_telling_and_timing_are_divinatory():
    divinatory = {key for key, _ in PASSAGE_ROLES if is_divinatory(key)}

    assert divinatory == {"advice.fortune_telling", "advice.timing"}
