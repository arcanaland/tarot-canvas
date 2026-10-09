ESOTERICA_TEXT = {
    # Between the values of an array, such as keywords
    "joiner": " · ",
    # Passages
    "theme": "Theme",
    "light": "Light",
    "shadow": "Shadow",
    "personality": "Personality",
    "approach": "Approach",
    "story": "Story",
    "x_mythical_spiritual": "Myth and Spirituality",
    "questions": "Questions to ask",
    "affirmation": "Affirmation",
    "x_note": "Note",
    "advice.relationships": "Relationships",
    "advice.work": "Work",
    "advice.spirituality": "Spirituality",
    "advice.personal_growth": "Personal growth",
    "x_marseille_image": "",
    "advice.fortune_telling": "A Potential Future",
    "advice.timing": "A Potential Time",
    "x_suit_cards": "The suit's cards",
    # Correspondences
    "number": "Number",
    "numerology": "Numerology",
    "x_numerology": "",
    "element": "Element",
    "elemental_dignity": "Elemental dignity",
    "x_elemental_dignity": "",
    "planet": "Planet",
    "zodiac": "Zodiac",
    "decan": "Decan",
    "astrology": "Astrology",
    "season": "Season",
    "direction": "Direction",
    "color": "Color",
    "archetype": "Archetype",
    "hebrew_letter": "Hebrew",
    "hebrew_letter_meaning": "",
    "hebrew_letter_value": "",
    "x_hebrew_letter_alt": "",
    # Families of rows
    "family.advice": "Advice",
    "family.symbols": "Symbols",
    "family.divinatory": "Divination",
    "family.correspondences": "Correspondences",
    "family.groups": "Groups",
    # A fold's header: its label and how many rows it holds
    "count": "{label} {count}",
    "show_menu": "Filter",
    "show_menu_tooltip": "Filter by category",
    # Groups; {suit} is the deck's word for the suit, {name} a source's own group
    "group.suits": "For the {suit}",
    "group.ranks": "For this rank",
    "group.classes.pip": "For the pips",
    "group.classes.court": "For the court",
    "group.arcana.major": "For the major arcana",
    "group.arcana.minor": "For the minor arcana",
    "group.all": "For every card",
    "group.custom": "{name}",
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
