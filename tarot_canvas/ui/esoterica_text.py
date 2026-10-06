ESOTERICA_TEXT = {
    # Between the values of an array, such as keywords
    "joiner": " · ",
    # Passages
    "theme": "",
    "light": "",
    "shadow": "",
    "personality": "",
    "approach": "",
    "story": "",
    "x_mythical_spiritual": "",
    "questions": "",
    "affirmation": "",
    "x_note": "",
    "advice.relationships": "",
    "advice.work": "",
    "advice.spirituality": "",
    "advice.personal_growth": "",
    "advice.fortune_telling": "",
    "advice.timing": "",
    "x_suit_cards": "",
    # Correspondences
    "number": "",
    "numerology": "",
    "x_numerology": "",
    "element": "",
    "elemental_dignity": "",
    "x_elemental_dignity": "",
    "planet": "",
    "zodiac": "",
    "decan": "",
    "astrology": "",
    "season": "",
    "direction": "",
    "color": "",
    "archetype": "",
    "hebrew_letter": "",
    "hebrew_letter_meaning": "",
    "hebrew_letter_value": "",
    "x_hebrew_letter_alt": "",
    # Families of rows
    "family.advice": "",
    "family.symbols": "",
    "family.divinatory": "",
    "family.correspondences": "",
    # Groups; {suit} is the deck's word for the suit, {name} a source's own group
    "group.suits": "",
    "group.ranks": "",
    "group.classes.pip": "",
    "group.classes.court": "",
    "group.arcana.major": "",
    "group.arcana.minor": "",
    "group.all": "",
    "group.custom": "",
}

# A registered key and its x_ spelling share one label
_SPELLINGS = {
    "numerology": "x_numerology",
    "x_numerology": "numerology",
    "elemental_dignity": "x_elemental_dignity",
    "x_elemental_dignity": "elemental_dignity",
}


def label_for(key):
    """The label for an entry, family or group key; empty hides what it labels."""
    return ESOTERICA_TEXT.get(key) or ESOTERICA_TEXT.get(_SPELLINGS.get(key), "") or ""
