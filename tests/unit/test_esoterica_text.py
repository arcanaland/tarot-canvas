from tarot_canvas.models import esoterica_registry
from tarot_canvas.ui.esoterica_text import ESOTERICA_TEXT, label_for

# These render as the source wrote them, with no label above. A symbol's heading, if it
# has one, is the source's own.
UNLABELLED = {"text", "keywords", "x_subtitle", "name"}


def test_every_key_the_registry_knows_has_a_label_entry():
    """So a new registry row can't render unlabelled by accident"""
    registered = {
        spelling
        for slot, spellings, _ in esoterica_registry._ORDER
        for spelling in spellings
        if slot != esoterica_registry.SYMBOLS and spelling not in UNLABELLED
    }

    assert registered - ESOTERICA_TEXT.keys() == set()


def test_an_unknown_key_has_no_label():
    assert label_for("x_nothing_registered") == ""


def test_the_two_spellings_share_a_label(monkeypatch):
    monkeypatch.setitem(ESOTERICA_TEXT, "numerology", "N")
    monkeypatch.setitem(ESOTERICA_TEXT, "x_numerology", "")

    assert label_for("x_numerology") == label_for("numerology") == "N"
