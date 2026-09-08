"""The conversion script is personal tooling, but its acceptance test is worth keeping."""

import importlib.util
import tomllib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "esoterica_0_1_to_1_0.py"

spec = importlib.util.spec_from_file_location("esoterica_0_1_to_1_0", SCRIPT)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


SOURCE = '''[meta]
schema_version = "1.0"
id = "tarot-for-change-book"
name = "Tarot for Change"
author = "Jessica Dore"
isbn13 = "978-0593295939"
publication_year = 2021

# A comment that must survive.

[passages.major_arcana.00]
text = """
First paragraph, with a quotation mark " in it.

Second paragraph.\\
"""

[passages.minor_arcana.wands.ace]
text = "The raw material of the suit."
'''


def test_headers_move_and_bodies_do_not():
    converted = converter.convert(SOURCE)

    before = tomllib.loads(SOURCE)["passages"]
    after = tomllib.loads(converted)["card"]

    assert after["major_arcana.00"]["passages"] == before["major_arcana"]["00"]
    assert after["minor_arcana.wands.ace"]["passages"] == before["minor_arcana"]["wands"]["ace"]
    assert "# A comment that must survive." in converted


def test_meta_is_carried_across_with_three_renames():
    meta = tomllib.loads(converter.convert(SOURCE))["meta"]

    assert "id" not in meta
    assert meta["isbn"] == "978-0593295939"
    assert meta["published_date"] == "2021"
    assert meta["author"] == "Jessica Dore"


def test_no_rights_assertion_is_invented():
    meta = tomllib.loads(converter.convert(SOURCE))["meta"]

    assert not {"license", "rights_status", "redistribution", "derivation"} & set(meta)


def test_a_file_with_nothing_to_convert_is_refused(tmp_path):
    path = tmp_path / "already.toml"
    path.write_text('[card."major_arcana.00".passages]\ntext = "Done."\n')

    with pytest.raises(converter.ConversionError, match="nothing to convert"):
        converter.main([str(path)])


def test_a_body_that_could_not_be_re_emitted_is_rejected():
    with pytest.raises(converter.ConversionError, match="backslash"):
        converter._check_convertible({"major_arcana.00": {"text": "trailing\\"}})

    with pytest.raises(converter.ConversionError, match='"""'):
        converter._check_convertible({"major_arcana.00": {"text": 'a """ b'}})


def test_conversion_round_trips_through_the_cli(tmp_path):
    source = tmp_path / "in.toml"
    source.write_text(SOURCE)
    destination = tmp_path / "out.toml"

    assert converter.main([str(source), str(destination)]) == 0

    cards = tomllib.loads(destination.read_text())["card"]
    assert set(cards) == {"major_arcana.00", "minor_arcana.wands.ace"}
