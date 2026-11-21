"""Validation through libarcana"""

import enum
import os
from dataclasses import dataclass


class Level(enum.IntEnum):
    """arcana_tarot's severity, in its order"""

    PEDANTIC = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    message: str
    card: str | None = None
    path: str | None = None
    key: str | None = None
    spec_url: str | None = None


@dataclass(frozen=True)
class LoadError:
    code: str
    message: str


@dataclass(frozen=True)
class Verdict:
    load_error: LoadError | None
    findings: tuple[Finding, ...]
    unchecked_rules: int

    @property
    def blocks(self):
        return self.load_error is not None or any(f.level >= Level.ERROR for f in self.findings)


def validate_deck(deck_dir):
    try:
        import arcana_tarot
    except ImportError as error:
        return Verdict(LoadError("import_error", str(error)), (), 0)

    unchecked = sum(
        1
        for rule in arcana_tarot.rules()
        if _state_name(arcana_tarot.state_of(rule.code)) in ("pending", "deferred")
    )
    try:
        deck = arcana_tarot.load_deck(os.fspath(deck_dir))
    except arcana_tarot.deck_error as error:
        code = getattr(error.code, "name", str(error.code))
        return Verdict(LoadError(code, error.message), (), unchecked)
    findings = tuple(_finding(arcana_tarot, d) for d in arcana_tarot.validate(deck))
    return Verdict(None, findings, unchecked)


def _state_name(state):
    return getattr(state, "name", None)


def _finding(arcana_tarot, diagnostic):
    return Finding(
        level=Level(int(diagnostic.level)),
        code=diagnostic.code,
        message=diagnostic.message,
        card=_text(diagnostic.card),
        path=_text(diagnostic.path),
        key=_text(diagnostic.key),
        spec_url=_spec_url(arcana_tarot, diagnostic.code),
    )


def _spec_url(arcana_tarot, code):
    rule = arcana_tarot.find_rule(code)
    citations = rule.citations() if rule is not None else []
    return arcana_tarot.spec_url(citations[0]) if citations else None


def _text(value):
    if value is None:
        return None
    return os.fspath(value) if isinstance(value, os.PathLike) else (str(value) or None)
