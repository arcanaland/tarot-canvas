from enum import Enum, auto


class Role(Enum):
    EPITHET = auto()
    KEYWORDS = auto()
    PRINCIPAL = auto()
    RANGE = auto()
    CHARACTER = auto()
    PROMPTS = auto()
    NOTES = auto()
    ADVICE = auto()
    SYMBOLS = auto()
    DIVINATORY = auto()
    CORRESPONDENCES = auto()
    GROUP_NOTES = auto()


# The roles whose rows sit together in one block, by the block's id
FAMILIES = {
    Role.ADVICE: "advice",
    Role.SYMBOLS: "symbols",
    Role.DIVINATORY: "divinatory",
    Role.CORRESPONDENCES: "correspondences",
}

# Every group's content, as one family
GROUPS = "groups"

PASSAGES = "passages"
CORRESPONDENCES = "correspondences"
SYMBOLS = "symbols"

# Every key in the symbols slot is a symbol
_ANY_SYMBOL = "*"

_ORDER = (
    (PASSAGES, ("x_subtitle",), Role.EPITHET),
    (PASSAGES, ("name",), Role.EPITHET),
    (PASSAGES, ("keywords",), Role.KEYWORDS),
    (PASSAGES, ("text",), Role.PRINCIPAL),
    (PASSAGES, ("theme",), Role.PRINCIPAL),
    (PASSAGES, ("light",), Role.RANGE),
    (PASSAGES, ("shadow",), Role.RANGE),
    (PASSAGES, ("personality",), Role.CHARACTER),
    (PASSAGES, ("approach",), Role.CHARACTER),
    (PASSAGES, ("story",), Role.CHARACTER),
    (PASSAGES, ("x_mythical_spiritual",), Role.CHARACTER),
    (PASSAGES, ("affirmation",), Role.PROMPTS),
    (PASSAGES, ("questions",), Role.PROMPTS),
    (PASSAGES, ("x_note",), Role.NOTES),
    (PASSAGES, ("advice.relationships",), Role.ADVICE),
    (PASSAGES, ("advice.work",), Role.ADVICE),
    (PASSAGES, ("advice.spirituality",), Role.ADVICE),
    (PASSAGES, ("advice.personal_growth",), Role.ADVICE),
    (SYMBOLS, (_ANY_SYMBOL,), Role.SYMBOLS),
    (PASSAGES, ("x_marseille_image",), Role.SYMBOLS),
    (PASSAGES, ("advice.fortune_telling",), Role.DIVINATORY),
    (PASSAGES, ("advice.timing",), Role.DIVINATORY),
    (CORRESPONDENCES, ("number",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("x_numerology", "numerology"), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("element",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("x_elemental_dignity", "elemental_dignity"), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("planet",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("zodiac",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("decan",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("astrology",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("season",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("direction",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("color",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("archetype",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("hebrew_letter",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("hebrew_letter_meaning",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("hebrew_letter_value",), Role.CORRESPONDENCES),
    (CORRESPONDENCES, ("x_hebrew_letter_alt",), Role.CORRESPONDENCES),
    # Unknown correspondences sort here
    (PASSAGES, ("x_suit_cards",), Role.GROUP_NOTES),
)

_POSITIONS = {
    (slot, spelling): (position, role)
    for position, (slot, spellings, role) in enumerate(_ORDER)
    for spelling in spellings
}

_LAST_CORRESPONDENCE = max(
    position for position, (slot, _, _) in enumerate(_ORDER) if slot == CORRESPONDENCES
)
_UNKNOWN_CORRESPONDENCE = _LAST_CORRESPONDENCE + 0.5
_UNKNOWN_PASSAGE = len(_ORDER)


def _lookup(slot, key):
    if slot == SYMBOLS:
        key = _ANY_SYMBOL
    return _POSITIONS.get((slot, key))


def role_of(slot, key):
    """The key's role, or None for a key the registry doesn't know."""
    found = _lookup(slot, key)
    return found[1] if found else None


def is_divinatory(key):
    """Whether a passage key is fortune-telling."""
    return role_of(PASSAGES, key) is Role.DIVINATORY


def sort_key(slot, key, file_index):
    found = _lookup(slot, key)
    if found:
        position = found[0]
    elif slot == CORRESPONDENCES:
        position = _UNKNOWN_CORRESPONDENCE
    else:
        position = _UNKNOWN_PASSAGE
    return (position, file_index)
