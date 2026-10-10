MAJOR_ARCANA_COUNT = 22

SUITS = ("wands", "cups", "swords", "pentacles")

PIPS = ("ace", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

COURTS = ("page", "knight", "queen", "king")


def _canonical_card_ids():
    ids = [f"major_arcana.{i:02d}" for i in range(MAJOR_ARCANA_COUNT)]
    for suit in SUITS:
        ids.extend(f"minor_arcana.{suit}.{rank}" for rank in PIPS + COURTS)
    return tuple(ids)


CANONICAL_CARD_IDS = _canonical_card_ids()


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
