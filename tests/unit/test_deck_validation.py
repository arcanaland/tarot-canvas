import builtins

import arcana_tarot
import pytest

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.deck_container import DECK_TOML
from tarot_canvas.models.deck_validation import Finding, Level, LoadError, Verdict, validate_deck


@pytest.fixture
def deck(tmp_path, curation_file):
    return writer.create("Test Deck", decks_root=tmp_path / "decks")


def unchecked_count():
    states = (arcana_tarot.state_of(rule.code) for rule in arcana_tarot.rules())
    return sum(
        1
        for state in states
        if state in (arcana_tarot.rule_state.pending, arcana_tarot.rule_state.deferred)
    )


def test_a_new_deck_passes(deck):
    verdict = validate_deck(deck)
    assert verdict.load_error is None
    assert not verdict.blocks
    assert verdict.unchecked_rules == unchecked_count()
    assert all(finding.level < Level.WARNING for finding in verdict.findings)


def test_a_deck_toml_that_is_not_toml_is_a_load_error(deck):
    (deck / DECK_TOML).write_text("not toml [[", encoding="utf-8")
    verdict = validate_deck(deck)
    assert verdict.load_error.code == "parse_error"
    assert verdict.blocks


def test_an_error_rule_blocks_and_cites_the_spec(deck):
    manifest = deck / DECK_TOML
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + '\n[card_backs]\ndefault = "nope"\n',
        encoding="utf-8",
    )
    rule = arcana_tarot.find_rule("unknown-default-card-back")
    assert arcana_tarot.state_of(rule.code) is arcana_tarot.rule_state.checked

    verdict = validate_deck(deck)

    errors = [finding for finding in verdict.findings if finding.level is Level.ERROR]
    assert [finding.code for finding in errors] == ["unknown-default-card-back"]
    assert errors[0].spec_url == arcana_tarot.spec_url(rule.citations()[0])
    assert errors[0].key == "card_backs.default"
    assert verdict.blocks


def test_no_arcana_tarot_is_a_load_error(deck, monkeypatch):
    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "arcana_tarot":
            raise ImportError("no arcana_tarot")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    verdict = validate_deck(deck)
    assert isinstance(verdict.load_error, LoadError)
    assert verdict.blocks


def test_levels_mirror_severity():
    assert [level.name.lower() for level in Level] == list(arcana_tarot.severity.__members__)
    assert [int(member) for member in arcana_tarot.severity.__members__.values()] == list(Level)


def test_a_warning_does_not_block():
    warning = Finding(Level.WARNING, "some-warning", "a warning")
    assert not Verdict(None, (warning,), 0).blocks
    assert Verdict(None, (Finding(Level.ERROR, "e", "m"),), 0).blocks
