"""The `[deck]` accessors the deck header reads, and its field-selection logic."""

from tarot_canvas.ui.widgets.deck_header import (
    DETAIL_FIELDS,
    detail_rows,
    format_date,
    format_value,
)


def test_reference_style_fields_are_all_exposed(minimal_deck):
    """A deck.toml that omits a field yields None, not a KeyError or an empty string."""
    assert minimal_deck.get_name() == "Minimal Test Deck"
    assert minimal_deck.get_version() == "1.0.0"
    for accessor in (
        "get_author",
        "get_license",
        "get_attribution",
        "get_publisher",
        "get_website",
        "get_deck_id",
        "get_schema_version",
        "get_created_date",
        "get_updated_date",
    ):
        assert getattr(minimal_deck, accessor)() is None, accessor
    assert minimal_deck.get_tags() == ()


def test_metadata_fields_returns_a_copy(minimal_deck):
    fields = minimal_deck.get_metadata_fields()
    fields["name"] = "mutated"
    assert minimal_deck.get_name() == "Minimal Test Deck"


def test_tags_survive_as_a_tuple_of_strings(minimal_deck):
    minimal_deck._metadata["deck"]["tags"] = ["classic", "", "reference"]
    assert minimal_deck.get_tags() == ("classic", "reference")


def test_blank_strings_read_as_absent(minimal_deck):
    minimal_deck._metadata["deck"]["license"] = ""
    assert minimal_deck.get_license() is None


def test_format_value_renders_scalars_and_lists():
    assert format_value("CC0") == "CC0"
    assert format_value(["a", "b"]) == "a, b"
    assert format_value(0.569) == "0.569"
    assert format_value(True) == "Yes"


def test_format_value_drops_empties_and_sub_tables():
    assert format_value(None) is None
    assert format_value("   ") is None
    assert format_value([]) is None
    assert format_value({"cards": ["major_arcana.00"]}) is None


def test_detail_rows_follow_the_declared_order():
    fields = {
        "id": "rws",
        "attribution": "Pamela Colman Smith",
        "license": "CC0",
        "name": "Rider-Waite-Smith",
    }
    assert [label for label, _, _ in detail_rows(fields)] == [
        "License",
        "Attribution",
        "Identifier",
    ]


def test_detail_rows_omit_what_the_collapsed_rows_already_show():
    keys = [key for _, _, key in detail_rows({"name": "N", "author": "A"})]
    assert keys == []


def test_the_description_leads_the_form_and_the_version_is_in_it():
    keys = [key for _, _, key in detail_rows({"version": "1.1", "description": "d"})]
    assert keys == ["description", "version"]


def test_dates_are_rendered_in_the_readers_locale():
    """ISO is a wire format; a deck page is read by a person."""
    rows = dict((key, value) for _, value, key in detail_rows({"created_date": "1909-12-01"}))
    assert rows["created_date"] != "1909-12-01"
    assert "1909" in rows["created_date"]
    assert "December" in rows["created_date"] or "12" in rows["created_date"]


def test_a_date_qt_cannot_parse_is_passed_through_as_written(qapp):
    """The spec does not forbid a partial date, and TOML permits a bare date literal."""
    assert format_date("1909") == "1909"
    assert format_date("sometime in 1909") == "sometime in 1909"
    assert format_date("2025-05-04") != "2025-05-04"


def test_the_formatted_date_carries_no_weekday(qapp):
    """A weekday is noise on a publication date, and Qt's en_US long form includes one."""
    assert "day," not in format_date("1909-12-01")


def test_unknown_keys_render_generically_after_the_known_ones():
    """A reference implementation shows a field it predates rather than dropping it."""
    rows = detail_rows({"license": "CC0", "aspect_ratio": 0.569, "future_key": "x"})
    assert rows == [
        ("License", "CC0", "license"),
        ("aspect_ratio", "0.569", "aspect_ratio"),
        ("future_key", "x", "future_key"),
    ]


def test_every_declared_field_has_a_human_label():
    assert all(label and label != key for key, label in DETAIL_FIELDS)
