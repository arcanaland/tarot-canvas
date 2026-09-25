"""Ranked card search: rank numerals, word order, shorthand and synonyms.

`CardTerms(card, deck_name).tier(Query(text))` is None when the card doesn't match,
otherwise a tier where lower ranks first:

    EXACT      the name, less "the"/"of", or shorthand such as 3oC or QoS
    PREFIX     the name starts with the query
    WORDS      every query word starts one of the card's own terms
    SYNONYMS   every query word matched, some only via a synonym, type or deck name
    SUBSTRING  the query appears anywhere in the name
"""

import re

EXACT, PREFIX, WORDS, SYNONYMS, SUBSTRING = range(5)

STOPWORDS = {"the", "of"}

RANK_NUMBERS = {
    "ace": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

# Other traditions' names, keyed by the canonical names the deck loader uses
SUIT_SYNONYMS = {
    "wands": ["rods", "staves", "staffs", "batons", "clubs"],
    "cups": ["chalices", "hearts"],
    "swords": ["blades", "spades"],
    "pentacles": ["coins", "disks", "discs", "diamonds"],
}

COURT_SYNONYMS = {
    "page": ["princess", "knave", "jack"],
    "knight": ["prince", "cavalier"],
}

# Thoth and other names for majors, keyed by canonical id
MAJOR_SYNONYMS = {
    "major_arcana.08": ["lust"],
    "major_arcana.11": ["adjustment"],
    "major_arcana.14": ["art"],
    "major_arcana.20": ["aeon", "judgment"],
    "major_arcana.21": ["universe"],
}

# Shorthand rank and suit letters, as in 3oC, QoS, KnW, 10P
SHORTHAND_RANKS = {"a": "ace", "p": "page", "kn": "knight", "q": "queen", "k": "king"}
SHORTHAND_RANKS.update({str(number): rank for rank, number in RANK_NUMBERS.items()})
SHORTHAND_SUITS = {"w": "wands", "c": "cups", "s": "swords", "p": "pentacles"}
SHORTHAND = re.compile(r"^(10|[1-9]|kn|[apqk])o?([wcsp])$")

_WORD = re.compile(r"[^\W_]+")


def words(text):
    return _WORD.findall((text or "").casefold())


def roman(number):
    if number == 0:
        return ""
    numerals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = []
    for value, letters in numerals:
        while number >= value:
            out.append(letters)
            number -= value
    return "".join(out)


def _significant(tokens):
    """The tokens less stopwords, unless stopwords are all there is"""
    kept = [token for token in tokens if token not in STOPWORDS]
    return kept or tokens


class Query:
    def __init__(self, text):
        self.text = (text or "").strip().casefold()
        self.tokens = _significant(words(text))
        self.joined = " ".join(self.tokens)

        compact = self.text.replace(" ", "")
        match = SHORTHAND.match(compact)
        self.shorthand = (
            (SHORTHAND_RANKS[match.group(1)], SHORTHAND_SUITS[match.group(2)]) if match else None
        )

    def __bool__(self):
        return bool(self.text)


class CardTerms:
    """What one card can be found by, computed once per card"""

    def __init__(self, card, deck_name=""):
        self.name = (card.get("name") or "").casefold()
        self.name_joined = " ".join(_significant(words(card.get("name"))))
        self.rank = card.get("rank")
        self.suit = card.get("suit")

        own = set(words(card.get("name")))
        own.update(words(self.suit))
        own.update(words(card.get("display_suit")))
        own.update(words(self.rank))
        own.update(words(card.get("display_rank")))

        numbers = set()
        number = card.get("number")
        if number is None:
            number = RANK_NUMBERS.get(self.rank)
        if number is not None:
            numbers.update({str(number), roman(number)} - {""})

        other = set(words(card.get("type", "").replace("_", " ")))
        other.update(words(deck_name))
        other.update(SUIT_SYNONYMS.get(self.suit, []))
        other.update(COURT_SYNONYMS.get(self.rank, []))
        other.update(MAJOR_SYNONYMS.get(card.get("id"), []))
        if card.get("display_rank"):
            other.add("court")

        self._own = own - STOPWORDS
        self._numbers = numbers
        self._other = other - STOPWORDS

    def _matches(self, token, terms):
        if token in self._numbers:
            return True
        # A digit names one number, so "1" must not find the tens
        if token.isdigit():
            return False
        return any(term.startswith(token) for term in terms)

    def tier(self, query):
        if not query:
            return EXACT
        if query.shorthand == (self.rank, self.suit):
            return EXACT
        if query.joined and query.joined == self.name_joined:
            return EXACT
        if query.joined and self.name_joined.startswith(query.joined):
            return PREFIX
        if query.tokens and all(self._matches(token, self._own) for token in query.tokens):
            return WORDS
        everything = self._own | self._other
        if query.tokens and all(self._matches(token, everything) for token in query.tokens):
            return SYNONYMS
        if query.text in self.name:
            return SUBSTRING
        return None
